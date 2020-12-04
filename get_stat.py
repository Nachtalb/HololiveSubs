#!/usr/bin/env python
# -*- coding: utf-8 -*-
from bilibili_api.user import UserInfo
from pathlib import Path
from twitter import Api
import json
import requests
import time


channels = [
    # Japan
    {'name': 'AZKi',              'bg': '#6cbabc', 'fg': '#fff', 'twitter':  'azki_vdiva',      'youtube': 'UC0TXe_LYZ4scaW2XMyi5_kw', 'bilibili': ''},
    {'name': 'Akai Haato',        'bg': '#eabb98', 'fg': '#fff', 'twitter':  'akaihaato',       'youtube': 'UC1CfXB_kRs3C-zaeTG3oGyg', 'bilibili': ''},
    {'name': 'Aki Rosenthal',     'bg': '#5deaf9', 'fg': '#fff', 'twitter':  'akirosenthal',    'youtube': 'UCFTLzh12_nrtzqBPsTCqenA', 'bilibili': ''},
    {'name': 'Amane Kanata',      'bg': '#2650d0', 'fg': '#fff', 'twitter':  'amanekanatach',   'youtube': 'UCZlDXzGoo7d44bwdNObFacg', 'bilibili': ''},
    {'name': 'Himemori Luna',     'bg': '#93446d', 'fg': '#fff', 'twitter':  'himemoriluna',    'youtube': 'UCa9Y57gfeY0Zro_noHRVrnw', 'bilibili': ''},
    {'name': 'Hoshimachi Suisei', 'bg': '#799acb', 'fg': '#fff', 'twitter':  'suisei_hosimati', 'youtube': 'UC5CwaMl1eIgY8h02uZw7u8A', 'bilibili': ''},
    {'name': 'Houshou Marine',    'bg': '#dc6e7f', 'fg': '#fff', 'twitter':  'houshoumarine',   'youtube': 'UCCzUftO8KOVkV4wQG1vkUvg', 'bilibili': ''},
    {'name': 'Inugami Korone',    'bg': '#c88382', 'fg': '#fff', 'twitter':  'inugamikorone',   'youtube': 'UChAnqc_AY5_I3Px5dig3X1Q', 'bilibili': ''},
    {'name': 'Kiryu Coco',        'bg': '#db9574', 'fg': '#fff', 'twitter':  'kiryucoco',       'youtube': 'UCS9uQI-jC3DE0L4IpXyvr6w', 'bilibili': ''},
    {'name': 'Minato Aqua',       'bg': '#793559', 'fg': '#fff', 'twitter':  'minatoaqua',      'youtube': 'UC1opHUrw8rvnsadT-iGp7Cg', 'bilibili': ''},
    {'name': 'Murasaki Shion',    'bg': '#4f3756', 'fg': '#fff', 'twitter':  'murasakishionch', 'youtube': 'UCXTpFs_3PqI41qX2d9tL2Rw', 'bilibili': ''},
    {'name': 'Nakiri Ayame',      'bg': '#bf8996', 'fg': '#fff', 'twitter':  'nakiriayame',     'youtube': 'UC7fk0CB07ly8oSl0aqKkqFg', 'bilibili': ''},
    {'name': 'Natsuiro Matsuri',  'bg': '#edad62', 'fg': '#fff', 'twitter':  'natsuiromatsuri', 'youtube': 'UCQ0UDLQCjY0rmuxCDE38FGg', 'bilibili': ''},
    {'name': 'Nekomata Okayu',    'bg': '#aa8caf', 'fg': '#fff', 'twitter':  'nekomataokayu',   'youtube': 'UCvaTdHTWBGv3MKj3KVqJVCw', 'bilibili': ''},
    {'name': 'Ookami Mio',        'bg': '#c6535c', 'fg': '#fff', 'twitter':  'ookamimio',       'youtube': 'UCp-5t9SrOQwXMU7iIjQfARg', 'bilibili': ''},
    {'name': 'Oozora Subaru',     'bg': '#6db2ce', 'fg': '#fff', 'twitter':  'oozorasubaru',    'youtube': 'UCvzGlP9oQwU--Y0r9id_jnA', 'bilibili': ''},
    {'name': 'Roboco San',        'bg': '#af7425', 'fg': '#fff', 'twitter':  'robocosan',       'youtube': 'UCDqI2jOz0weumE8s7paEk6g', 'bilibili': ''},
    {'name': 'Sakura Miko',       'bg': '#f6a1a8', 'fg': '#fff', 'twitter':  'sakuramiko35',    'youtube': 'UC-hM6YJuNYVAmUWxeIr9FeA', 'bilibili': ''},
    {'name': 'Shirakami Fubuki',  'bg': '#5eb6d0', 'fg': '#fff', 'twitter':  'shirakamifubuki', 'youtube': 'UCdn5BQ06XqgXoAxIhbqw5Rg', 'bilibili': ''},
    {'name': 'Shiranui Flare',    'bg': '#5bb39d', 'fg': '#fff', 'twitter':  'shiranuiflare',   'youtube': 'UCvInZx9h3jC2JzsIzoOebWg', 'bilibili': ''},
    {'name': 'Shirogane Noel',    'bg': '#dccdcd', 'fg': '#fff', 'twitter':  'shiroganenoel',   'youtube': 'UCdyqAaZDKHXg4Ahi7VENThQ', 'bilibili': ''},
    {'name': 'Tokino Sora',       'bg': '#be6c5e', 'fg': '#fff', 'twitter':  'tokino_sora',     'youtube': 'UCp6993wxpyDPHUpavwDFqgg', 'bilibili': ''},
    {'name': 'Tokoyami Towa',     'bg': '#d197ce', 'fg': '#fff', 'twitter':  'tokoyamitowa',    'youtube': 'UC1uv2Oq6kNxgATlCiez59hw', 'bilibili': ''},
    {'name': 'Tsunomaki Watame',  'bg': '#e4d3a3', 'fg': '#fff', 'twitter':  'tsunomakiwatame', 'youtube': 'UCqm3BQLlJfvkTsX_hvm0UmA', 'bilibili': ''},
    {'name': 'Uruha Rushia',      'bg': '#80d3c3', 'fg': '#fff', 'twitter':  'uruharushia',     'youtube': 'UCl_gCybOJRIgOXw6Qb4qJzQ', 'bilibili': ''},
    {'name': 'Usada Pekora',      'bg': '#acc0ee', 'fg': '#fff', 'twitter':  'usadapekora',     'youtube': 'UC1DCedRgGHBdm81E1llLhOQ', 'bilibili': ''},
    {'name': 'Yozora Mel',        'bg': '#d7a86a', 'fg': '#fff', 'twitter':  'yozoramel',       'youtube': 'UCD8HOxPs4Xvsm8H0ZxXGiBw', 'bilibili': ''},
    {'name': 'Yuzuki Choco',      'bg': '#eb9f74', 'fg': '#fff', 'twitter':  'yuzukichococh',   'youtube': 'UC1suqwovbL1kzsoaZgFZLKg', 'bilibili': ''},
    # Indonesia
    {'name': 'Airani Iofifteen',  'bg': '#be8b8f', 'fg': '#fff', 'twitter':  'airaniiofifteen', 'youtube': 'UCAoy6rzhSf4ydcYjJw3WoVg', 'bilibili': ''},
    {'name': 'Ayunda Risu',       'bg': '#d48d85', 'fg': '#fff', 'twitter':  'ayunda_risu',     'youtube': 'UCOyYb1c43VlX9rc_lT6NKQw', 'bilibili': ''},
    {'name': 'Moona Hoshinova',   'bg': '#9b85c1', 'fg': '#fff', 'twitter':  'moonahoshinova',  'youtube': 'UCP0BspO_AMEe3aQqqpo89Dg', 'bilibili': ''},
    # China
    {'name': 'Artia',             'bg': '#736b99', 'fg': '#fff', 'twitter':  'artia_hololive',  'youtube': '', 'bilibili': '511613155'},
    {'name': 'Civia',             'bg': '#67abd5', 'fg': '#fff', 'twitter':  'civia_hololive',  'youtube': '', 'bilibili': '354411419'},
    {'name': 'Doris',             'bg': '#8198c8', 'fg': '#fff', 'twitter':  'doris_hololive',  'youtube': '', 'bilibili': '511613156'},
    {'name': 'Rosalyn',           'bg': '#314268', 'fg': '#fff', 'twitter':  'rosalyn_holocn',  'youtube': '', 'bilibili': '511613157'},
    {'name': 'Spade Echo',        'bg': '#bb88a1', 'fg': '#fff', 'twitter':  'spadeecho',       'youtube': '', 'bilibili': '456368455'},
    {'name': 'Yogiri',            'bg': '#bd536e', 'fg': '#fff', 'twitter':  'yogiri_hololive', 'youtube': '', 'bilibili': '427061218'},
]

# YouTube
parts = ['statistics']
yt_key = ''
yt_url = 'https://www.googleapis.com/youtube/v3/channels?part={parts}&id={channels}&key={key}'

ids = filter(None, map(lambda data: data['youtube'], channels))
yt_data = requests.get(yt_url.format(
    parts=','.join(parts),
    channels=','.join(ids),
    key=yt_key,
)).json()

# Twitter
twitter_api = Api(consumer_key='',
                  consumer_secret='',
                  access_token_key='',
                  access_token_secret='')

t_data = twitter_api.GetListMembersPaged('')[2]

# Sort and gather data
result = []
for channel_data in channels:
    t_user = next(filter(lambda t: t.screen_name.lower() == channel_data['twitter'], t_data))
    channel_data['image'] = t_user.profile_image_url_https.replace('_normal', '')
    channel_data['t_subs'] = int(t_user.followers_count)

    b_user, yt_user= None, None

    if channel_data['bilibili']:
        b_user = UserInfo(channel_data['bilibili']).get_info()
        channel_data['b_subs'] = int(b_user['follower'])
    if channel_data['youtube']:
        yt_user = next(filter(lambda yt: yt['id'] == channel_data['youtube'], yt_data['items']))
        channel_data['yt_subs'] = int(yt_user['statistics']['subscriberCount'])

    if yt_user:
        channel_data['main_subs'] = 'yt_subs'
    elif b_user:
        channel_data['main_subs'] = 'b_subs'
    else:
        channel_data['main_subs'] = 't_subs'

result = sorted(channels, reverse=True, key=lambda data: data[data['main_subs']])
# Write stats
data_file = Path(__file__).absolute().parent / 'www/stats'
data_file.write_text(json.dumps(result))
print(time.asctime())
