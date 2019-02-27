import json
import re
import requests
from dateutil import parser
from piazza_api import Piazza

import config


def get_post_last_change(post_id):
    return 'a'


def set_post_last_change(post_id, last_change):
    pass


def send_to_slack(payload):
    requests.post(url=config.slack_hook_url, json=payload)


def connect_to_piazza():
    p = Piazza()
    p.user_login(email=config.piazza_email, password=config.piazza_password);
    return p.network(network_id=config.piazza_class_id)


## todo improve html decoding

def strip_p_html(str):
    return re.sub(r'</?p>', '', str)


def strip_all_html(str):
    return re.sub(r'</?\w+>', '', str)


def entity_to_attachment(entity):
    event = entity["event"]
    when = parser.isoparse(entity["when"])
    user = entity["user"]
    content = entity["content"]

    attachment = dict()
    if event == "create":
        attachment["color"] = "danger"
        attachment["pretext"] = "New Post - {}".format(content["subject"])
    elif event == "update":
        attachment["color"] = "warning"
        attachment["pretext"] = "Update in Post - {}".format(content["subject"])
    elif event == "followup":
        attachment["color"] = "#439FE0"
        attachment["pretext"] = "A followup to Post - {}".format(content["parent_subject"])
    elif event == "feedback":
        attachment["color"] = "good"
        attachment["pretext"] = "A feedback to Followup - {}".format(content["parent_subject"])
    else:
        attachment["color"] = "#DDDDDD"
        attachment["pretext"] = "Something else? - {}".format(content.get("parent_subject", content["subject"]))

    attachment["fallback"] = strip_all_html(content["content"])
    attachment["title"] = strip_all_html(content["subject"])
    # attachment["title_link"] = 'there's no link for individual feedbacks/followups
    attachment["text"] = strip_p_html(content["content"])
    attachment["footer"] = "{} ~ {} ~ {}".format(user["name"], user["class_sections"], user["role"])
    if user["photo_url"]:
        attachment["footer_icon"] = user["photo_url"]
    attachment["ts"] = int(when.timestamp())

    return attachment


def parse_post(p, post_id):
    last_change = get_post_last_change(post_id)
    post = p.get_post(post_id)
    change_log = post["change_log"]
    if change_log[-1]["when"] == last_change:
        return

    children = dict()
    children[post["created"]] = children[post["history"][-1]["created"]] = {
        "parent_subject": None,
        "data": post["data"],
        "subject": post["history"][-1]["subject"],
        "content": post["history"][-1]["content"],
        "folders": post["folders"],
        "type": post["type"]
    }
    for followup in post["children"]:
        children[followup["created"]] = children[followup["updated"]] = {
            "parent_subject": post["history"][-1]["subject"],
            "data": followup["data"],
            "subject": strip_all_html(followup["subject"])[:40],
            "content": followup["subject"],
            "folders": followup["folders"],
            "type": "followup"
        }
        for feedback in followup["children"]:
            children[feedback["created"]] = children[feedback["updated"]] = {
                "parent_subject": strip_all_html(followup["subject"])[:40],
                "data": feedback["data"],
                "subject": strip_all_html(feedback["subject"])[:40],
                "content": feedback["subject"],
                "type": "feedback"
            }

    new_entities = []
    related_users = []
    for change in reversed(change_log):
        if change["when"] == last_change:
            break
        if change["type"] in ["create", "update"]:
            change["data"] = post["id"]
        try:
            new_entities.append({
                "uid": change["uid"],
                "event": change["type"],
                "when": change["when"],
                "content": children[change["when"]]
            })
        except KeyError:
            print(change, "failed")

        related_users.append(change["uid"])
    new_entities.reverse()

    users = dict()
    user_list = p.get_users(related_users)
    for user in user_list:
        users[user["id"]] = {
            "name": user["name"],
            "role": user["role"],
            "class_sections":  ', '.join(user.get("class_sections", "")),
            "photo_url": user.get("photo_url", None)
        }

    attachments = []
    for entity in new_entities:
        entity["user"] = users[entity["uid"]]
        attachments.append(entity_to_attachment(entity))

    tags = ", ".join(map(lambda tag: "({})".format(tag), post.get("tags", [])))
    text = "<https://piazza.com/class/{}?cid={}|{}> {}"\
        .format(config.piazza_class_id, post_id, post["history"][-1]["subject"], tags)

    message = {
        "text": text,
        "attachments": attachments
    }
    return message


def runner():
    p = connect_to_piazza()

    message = parse_post(p, 7)
    send_to_slack(message)
    # stuff = p.get_post(7)
    f = open("tmp", "w")
    json.dump(message, f)


runner()
