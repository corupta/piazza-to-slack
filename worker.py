import json
import re
import requests
from dateutil import parser
from piazza_api import Piazza
from htmlslacker import HTMLSlacker
from urllib.parse import urlparse
import time
import redis

import config


def connect_to_redis():
    url = urlparse(config.redis_cloud_url)
    return redis.Redis(host=url.hostname, port=url.port, password=url.password)


def connect_to_piazza():
    p = Piazza()
    p.user_login(email=config.piazza_email, password=config.piazza_password)
    return p.network(network_id=config.piazza_class_id)


def get_post_last_change(r, post_id):
    key = "POST-{}".format(post_id)
    try:
        return r.get(key)
    except redis.RedisError:
        print("Redis Error on get post last change on {}".format(key))
        return ""


def set_post_last_change(r, post_id, last_change):
    key = "POST-{}".format(post_id)
    try:
        return r.set(key, last_change)
    except redis.RedisError:
        print("Redis Error on set post last change on {}".format(key))


def send_to_slack(payload):
    requests.post(url=config.slack_hook_url, json=payload)


def parse_content(content):
    content = re.sub(r'<strong>(\W*)</strong>', r'\g<1>', content)
    content = re.sub(r'<(/?)p>', r'<\g<1>span>', content)
    content = re.sub(r'(</li>|<ol>|<ul>|\n)', r'\g<1><br />', content)
    return HTMLSlacker(content).get_output()


def parse_subject(subject):
    return re.sub(r'\n+', ' ', subject)[:20]


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

    attachment["fallback"] = content["content"]
    if content["subject"]:
        attachment["title"] = content["subject"]
    # attachment["title_link"] = 'there's no link for individual feedbacks/followups
    attachment["text"] = content["content"]
    attachment["footer"] = "{} ~ {} ~ {}".format(user["name"], user["class_sections"], user["role"])
    if user["photo_url"]:
        attachment["footer_icon"] = user["photo_url"]
    attachment["ts"] = int(when.timestamp())
    attachment["mrkdwn_in"] = ["text"]

    return attachment


def parse_post(r, p, post):
    post_id = post["nr"]
    last_change = get_post_last_change(r, post_id)
    change_log = post["change_log"]
    if change_log[-1]["when"] == last_change:
        return
    set_post_last_change(r, post_id, change_log[-1]["when"])

    children = dict()
    children[post["created"]] = children[post["history"][-1]["created"]] = {
        "parent_subject": None,
        "data": post["data"],
        "subject": parse_content(post["history"][-1]["subject"]),
        "content": parse_content(post["history"][-1]["content"]),
        "folders": post["folders"],
        "type": post["type"]
    }
    for followup in post["children"]:
        followup_content = parse_content(followup["subject"])
        children[followup["created"]] = children[followup["updated"]] = {
            "parent_subject": parse_subject(children[post["created"]]["subject"]),
            "data": followup["data"],
            "subject": None,
            "content": followup_content,
            "folders": followup["folders"],
            "type": "followup"
        }
        for feedback in followup["children"]:
            feedback_content = parse_content(feedback["subject"])
            children[feedback["created"]] = children[feedback["updated"]] = {
                "parent_subject": parse_subject(followup_content),
                "data": feedback["data"],
                "subject": None,
                "content": feedback_content,
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
            "class_sections":  ', '.join(map(lambda x: x[:8], user.get("class_sections", []))),
            "photo_url": user.get("photo_url", None)
        }

    attachments = []
    for entity in new_entities:
        entity["user"] = users[entity["uid"]]
        attachments.append(entity_to_attachment(entity))

    tags = " ".join(map(lambda tag: "`{}`".format(tag), post.get("tags", [])))
    text = "<https://piazza.com/class/{}?cid={}|{}> {}"\
        .format(config.piazza_class_id, post_id, post["history"][-1]["subject"], tags)

    message = {
        "text": text,
        "attachments": attachments
    }
    return message


def runner(sleep_duration):
    r = connect_to_redis()
    p = connect_to_piazza()

    while True:
        posts = p.iter_all_posts()
        for post in posts:
            message = parse_post(r, p, post)
            send_to_slack(message)
            time.sleep(sleep_duration)


runner(config.sleep_duration)
