import praw

username = ''
password = ''
version = 'v0.5.0'
subreddit = ''

ts = 'time.ctime(int(time.time()))'

r = praw.Reddit(user_agent=username + ' for ' + subreddit + '/' + version + ' by teaearlgraycold')