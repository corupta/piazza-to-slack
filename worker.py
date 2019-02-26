import requests
import json
import re
from piazza_api import Piazza

import config

def get_post_last_change(post_id):
    return "2019-02-11T10:48:22Z"

def set_post_last_change(post_id, last_change):

def send_to_slack(payload, attachments):
    print('hi')

def connect_to_piazza():
    p = Piazza()
    p.user_login(email=config.piazza_email, password=config.piazza_password);
    return p.network(network_id=config.piazza_class_id)

def entity_to_attachment(entity):
    event = entity.event
    when = entity.when
    user = entity.user
    content = entity.content

    attachment = dict()
    attachment.author_name = "{} ~ {} ({})".format(user.name, user.class_sections, user.role)
    if event == "create":
        attachment.color = "danger"
        attachment.pretext = "New Post - {}".format(content.subject)
    elif event == "update":
        attachment.color = "warning"
        attachment.pretext = "Update in Post - {}".format(content.subject)
    elif event == "followup":
        attachment.color = "#439FE0"
        attachment.pretext = "A followup to Post - {}".format(content.parent_subject)
    elif event == "feedback":
        attachment.color = "good"
        attachment.pretext = "A feedback to Followup - {}".format(content.parent_subject)
    else:
        attachment.color = "#DDDDDD"
        attachment.pretext = "Something else? - {}".format(content.parent_subject or content.subject)




def parse_post(p, post_id):
    last_change = get_post_last_change(post_id)
    post = p.get_post(post_id)
    change_log = post.change_log
    if change_log[-1].when == last_change:
        return

    children = dict()
    children[post.id] = {
        "parent_subject": None,
        "parent": None,
        "data": post.data,
        "subject": post.history[-1].subject,
        "content": post.history[-1].content,
        "folders": post.folders,
        "type": post.type
    }
    for followup in post.children:
        children[followup.id] = {
            "parent_subject": post.history[-1].subject,
            "parent": post.id,
            "data": followup.data,
            "subject": followup.subject[:40],
            "content": followup.subject,
            "folders": followup.folders,
            "type": "followup"
        }
        for feedback in followup.children:
            children[feedback.id] = {
                "parent": followup.id,
                "parent_subject": followup.subject[:40],
                "data": feedback.data,
                "subject": feedback.subject[:40],
                "content": feedback.subject,
                "type": "feedback"
            }

    new_contents = []
    related_users = []
    for change in change_log.reversed():
        if change.when == last_change:
            break
        new_contents.append({
            "uid": change.uid,
            "event": change.type,
            "when": change.when,
            "content": children[change.data]
        })
        related_users.append(change.uid)
    new_contents.reverse()

    users = dict()
    user_list = p.get_users(related_users)
    for user in user_list:
        users[user.id] = {
            "name": user.name,
            "role": user.role,
            "class_sections":  ', '.join(user.class_sections)
        }

    for content in new_contents:
        content.user = users[content.uid]
    tags = post.tags



def runner():
    p = connect_to_piazza()
    posts = p.get_post(1)
    f = open("tmp", "w")
    json.dump(posts, f)

runner();
