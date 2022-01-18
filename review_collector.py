import feedparser

KNOWN_REVIEWS = {
    "YARN-10284",
    "YARN-10327",
    "YARN-10325",
    "YARN-10507",
    "YARN-10579",
    "YARN-10581",
    "YARN-10490",
    "YARN-10515",
    "YARN-10600",
    "YARN-10635",
    "YARN-10636",
    "YARN-10627",
    "YARN-10532",
    "YARN-9618",
    "YARN-10807",
    "YARN-10833",
    "YARN-10869",
    "YARN-10814",
    "YARN-10891",
    "YARN-10576",
    "YARN-10522",
    "YARN-10646",
    "YARN-10872",
    "YARN-10917",
    "YARN-10961",
    "YARN-1115",
    "YARN-10904",
    "YARN-10985",
    "YARN-11006",
    "YARN-10982",
    "YARN-11024",
    "YARN-10907",
    "YARN-10929",
    "YARN-10963",
    "YARN-10427",
    "YARN-6862",
}

ADDITIONAL_REVIEWS = {
    "YARN-10178",
    "YARN-6221",
    "YARN-10787",
    "YARN-10796",
    "YARN-10779",
    "YARN-10761",
    "YARN-9927",
    "YARN-10739",
    "YARN-10637",
    "YARN-10723",
    "YARN-10657",
    "YARN-10503",
    "YARN-10674",
    "YARN-10702",
    "YARN-10701",
    "YARN-10659",
    "YARN-10497",
    "YARN-10687",
    "YARN-10639",
    "YARN-10641",
    "YARN-10652",
    "YARN-10632",
    "YARN-10620",
    "YARN-10610",
    "YARN-10547",
    "YARN-10585",
    "YARN-10512",
}

if __name__ == '__main__':
    d = feedparser.parse("activity_feed.xml")
    comments = list(filter(lambda feed: 'commented on' in feed['title'], d.entries))
    comment_table = dict()
    for comment in comments:
        jira = comment['link'].split("/")[5]
        if jira not in KNOWN_REVIEWS:
            comment_table[jira] = comment_table.get(jira, "") + "\n" + comment.content[0].value

    table = str.join("\n", [jira + "<hr>\n" + content for jira, content in comment_table.items()])
    with open("review_res.html", "w") as file:
        file.write(table)
