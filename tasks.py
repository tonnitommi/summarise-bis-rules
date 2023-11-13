from urllib.parse import urljoin
from robocorp.tasks import task
from robocorp import vault, storage
from robocorp.storage._client import AssetNotFound
from bs4 import BeautifulSoup
import requests
from RPA.HTTP import HTTP
from RPA.PDF import PDF
from RPA.Notifier import Notifier
from openai import OpenAI


@task
def summarize_new_things():
    try:
        bis_docs = storage.get_json("bis-docs")
    except AssetNotFound as e:
        bis_docs = []

    links = get_bis_rule_doc_links()
    for url in links:
        if url in bis_docs:
            print(f"URL {url} already summarized - skipping")
            continue
        print(f"Summarizing URL {url}")
        summary = summarize_doc(url)
        slack_it(summary, url)
        bis_docs.append(url)
        storage.set_json("bis-docs", bis_docs)


def summarize_doc(url: str) -> str:
    openai_secret = vault.get_secret("OpenAI")

    client = OpenAI(
        api_key=openai_secret["key"]
    )
    # Set Robocorp libs up
    http = HTTP()
    pdf = PDF()

    filename = "files/" + url.split('=')[-1] + ".pdf"
    http.download(url, filename)

    # then read the text
    text = pdf.get_text_from_pdf(filename)

    for page_number, content in text.items():
        rule_string = f'Page {page_number}:'
        rule_string = rule_string + content
        rule_string = rule_string + '\n---\n'

    completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "You are an assistant for the enterprise legal team, helping them to understand the newly updated Federal Buereau of Industry and Security rules and notifications.",
            },
            {
                "role": "user",
                "content": "Your task is to summarize the new rule or notification by the BIS, and highlight the parts that might be most relevant for global enterprise operations. Try avoiding to include the boilerplate language in your summary, but to focus directly on the actual relevant content. Aim for a summary that can be consumed by a legal person in less than a minute. Never drop relevant entity names, or enforcement dates from your summary. Always start with a one liner of what the rule or notice is about, followed by an empty line.\n\nBIS RULE CONTENT:\n" + rule_string,
            }
        ],
        model="gpt-4-1106-preview",
    )

    return completion.choices[0].message.content


def get_bis_rule_doc_links() -> list[str]:
    base_url = "https://www.bis.doc.gov/"
    response = requests.get(f"{base_url}index.php/federal-register-notices")
    soup = BeautifulSoup(response.content, 'html.parser')
    links = soup.find_all('a', text=lambda text: text and "BIS Rule" in text)
    return [urljoin(base_url, link.get('href')) for link in links]


def slack_it(message, link):
    slack_secrets = vault.get_secret("Slack")
    notif = Notifier()
    notif.notify_slack(
        message=f"NEW BIS NOTIFICATION SUMMARY:\n\n{message}\n\nLink: {link}",
        channel=slack_secrets["channel"],
        webhook_url=slack_secrets["webhook"]
    )
