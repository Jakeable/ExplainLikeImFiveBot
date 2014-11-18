import time    #Allows the program to use the sleep() command
import datetime#Makes it easy to compute the deltaT in days
import re      #Allows the program to use Regular Expressions
import praw    #A wrapper for the reddit API. Provides all of the reddit-related methods
import json

import sys     #Used solely for sys.exit()
import logging #Used for error reporting/debugging

import urllib  #Used to encode strings for use in URLs
from HTMLParser import HTMLParser

import bot     #Stores bot config

cache_timouts = {'modmail': 0, 'inbox': 0, 'automoderator_wiki': 0, 'usernotes_wiki': 0}
message_backlog = []

#Subreddit parameter is required to check for moderators
def check_pms(subreddit):
    global cache_timouts
    global message_backlog

    parser = HTMLParser()

    if (time.time() - cache_timouts['inbox']) > bot.r.config.cache_timeout + 1:
        cache_timouts['inbox'] = time.time()

        for message in bot.r.get_unread(limit=None):        
            #Perform checks on top level message            
            if message.new == True:
                message.mark_as_read()

                if str(message.author) == 'AutoModerator':
                    unesc_body = parser.unescape(message.body)

                    if message.subject == 'AutoModerator conditions updated':
                        message_backlog[-1].reply(unesc_body)
                        del message_backlog[-1]

                    else:
                        bot.r.send_message('/r/' + str(subreddit), 'AutoModerator Message', unesc_body)

                    printlog('AutoModerator response relayed')

                #elif message.author in subreddit.get_moderators():
                    #message_commands(message, subreddit)

def check_modmail(subreddit):
    global cache_timouts

    parser = HTMLParser()

    sub_prefix = re.compile(ur'^[\[\()]?eli[5f]\s?[:-\]\)]?\s?', re.IGNORECASE)
    report_check = re.compile(ur'report', re.IGNORECASE)

    if (time.time() - cache_timouts['modmail']) > bot.r.config.cache_timeout + 1:
        cache_timouts['modmail'] = time.time()

        for modmail in subreddit.get_mod_mail(limit=6):        
            #Perform checks on top level modmail            
            if modmail.new == True:
                modmail.mark_as_read()

                if report_check.search(modmail.subject) == None and sub_prefix.search(modmail.subject) != None and len(modmail.subject) > 6:
                    #Make certain that the text can be put into a url/markdown code safely
                    unesc_subject = parser.unescape(modmail.subject)
                    unesc_body = parser.unescape(modmail.body)
                    
                    safe_subject = urllib.quote_plus(unesc_subject.encode('utf-8'))
                    safe_body = urllib.quote_plus(unesc_body.encode('utf-8'))
                    
                    modmail.reply('It appears that you have accidentally posted a question in modmail rather than create a new submission.\n\n[Click Here](http://www.reddit.com/r/explainlikeimfive/submit?selftext=true&title=' + safe_subject + '&text=' + safe_body +') to turn this modmail into a submission.\n\nPlease [check our rules for posting](http://reddit.com/r/explainlikeimfive/wiki/rules) while you are at it and make sure your submission is a good fit for ELI5.')
                    printlog('Sent modmail to ' + str(modmail.author) + ' about accidental ELI5 thread in modmail')

                if modmail.distinguished == 'moderator':
                    message_commands(modmail, subreddit)

            #Perform checks on modmail replies
            for reply in modmail.replies:
                if reply.new == True:
                    reply.mark_as_read()

                    if reply.distinguished == 'moderator':
                        message_commands(reply, subreddit)

def message_commands(message, subreddit):
    global cache_timouts
    global message_backlog

    parser = HTMLParser()

    url_verifier = re.compile(ur'(https?://(?:www.)?reddit.com/r/explainlikeimfive/comments/([A-Za-z\d]{6})/[^\s]*)')
    comment_finder = re.compile(ur'---\n\n?([\S\s]*?)\n\n?---')

    automod_jobs = []
    automod_jobs.append([])
    automod_jobs.append([])

    usernotes_jobs = []
    usernotes_jobs.append([])
    usernotes_jobs.append([])

    shadowban_reason = ''

    command_finder = re.compile(ur'^!([^\s].*)$', re.MULTILINE)
    matches = re.findall(command_finder, message.body)

    for group in matches:
        command = group.split(' ')

        if command[0].lower() == 'shadowban':
            try:
                automod_jobs[0].append('shadowban')
                automod_jobs[1].append(command[1])

                shadowban_reason = ' '.join(command[2:])

                usernotes_jobs[0].append(command[1])
                usernotes_jobs[1].append(shadowban_reason)

                if len(command) == 2:
                    message.reply('User [**' + command[1] + '**](http://reddit.com/user/' + command[1] + ') has been shadowbanned.')
                else:
                    message.reply('User [**' + command[1] + '**](http://reddit.com/user/' + command[1] + ') has been shadowbanned for *' + shadowban_reason + '*.')

                print('[' + eval(bot.ts) + '] ' + command[1] + ' pending shadowban')

            except:
                printlog('Error while responding to shadowban command for ' + command[1])

        elif command[0].lower() == 'ban':
            if len(command) == 2:
                try:
                    user = bot.r.get_redditor(command[1])
                    subreddit.add_ban(user)

                    message.reply('User **' + command[1] + '** has been banned')
                except Exception,e:
                    printlog('Error while banning ' + command[1] + ': ' + str(e))

            else:
                message.reply('**Syntax Error**:\n\n    !Ban username')

        elif command[0].lower() == 'lock':
            if len(command) >= 2:
                url_matches = re.search(url_verifier, command[1])

                if url_matches != None:
                    permalink = url_matches.groups(0)[0]
                    thread_id = url_matches.groups(0)[1]

                    automod_jobs[0].append('lock')
                    automod_jobs[1].append(thread_id)

                    try:
                        modteam = praw.Reddit(user_agent=bot.useragent)
                        modteam.login(bot.modteam, bot.modteampw)

                        locked_thread = praw.objects.Submission.from_url(modteam, permalink)
                        locked_thread.set_flair('Locked')

                        comment_matches = re.search(comment_finder, message.body)

                        if comment_matches != None:
                            body_text = comment_matches.groups(0)[0]

                            new_comment = locked_thread.add_comment(body_text)
                            new_comment.distinguish()

                            message.reply('[**' + locked_thread.title + '**](' + locked_thread.permalink + ') has been locked.\n\nTo view the comment automatically made in the thread [click here](' + new_comment.permalink + ').')
                        else:
                            message.reply('[**' + locked_thread.title + '**](' + locked_thread.permalink + ') has been locked.\n\nPlease post a comment explaining why it has been locked.')
                            
                        printlog('Locked ' + thread_id)

                        del modteam

                    except Exception,e:
                        printlog('Error while locking ' + thread_id + ': ' + str(e))

                else:
                    message.reply('**Error:**\n\nMalformed URL: ' + command[1] + '\n\nAcceptable format: http://www.reddit.com/r/explainlikeimfive/comments/linkid/title')
                    printlog('Malformed URL for thread lock by ' + str(message.author) + ': ' + command[1])

            else:
                message.reply('**Syntax Error**:\n\n    !lock threadURL')

        elif command[0].lower() == 'sticky':
            if len(command) >= 2:
                try:
                    modteam = praw.Reddit(user_agent=bot.useragent)
                    modteam.login(bot.modteam, bot.modteampw)
                    
                    comment_matches = re.search(comment_finder, message.body)

                    if comment_matches != None:
                        body_text = comment_matches.groups(0)[0]
                        url_matches = re.search(url_verifier, command[1])

                        if url_matches == None:
                            title = ' '.join(command[1:])

                            stickied_thread = modteam.submit(subreddit, title, text=body_text)
                            stickied_thread.set_flair('Official Thread')
                            stickied_thread.sticky()

                            message.reply('[**' + stickied_thread.title + '**](' + stickied_thread.permalink + ') has been stickied.\n\n')

                            printlog('Successfully stickied thread: ' + title)

                        else:
                            permalink = url_matches.groups(0)[0]

                            stickied_thread = praw.objects.Submission.from_url(modteam, permalink)
                            stickied_thread.set_flair('Official Thread')
                            stickied_thread.sticky()

                            new_comment = stickied_thread.add_comment(comment_matches.groups(0)[0])
                            new_comment.distinguish()

                            message.reply('[**' + stickied_thread.title + '**](' + stickied_thread.permalink + ') has been stickied.\n\nTo view the comment automatically made in the thread [click here](' + new_comment.permalink + ').')
                            
                            printlog('Successfully stickied thread: ' + stickied_thread.title)

                    else:
                        message.reply('You must provide text for the sumission. The format for a sticky is:\n\n    !sticky title|link\n    ---\n    Post Body\n    ---')

                    del modteam

                except Exception,e:
                    printlog('Error while sticky-ing thread: ' + str(e))

            else:
                message.reply('**Syntax Error**:\n\n    !sticky title|link\n    ---\n    Post Body\n    ---')

        elif command[0].lower() == 'summary':
            if len(command) > 1:
                try:
                    if (time.time() - cache_timouts['usernotes_wiki']) < bot.r.config.cache_timeout + 1:
                        time.sleep(int(time.time() - cache_timouts['usernotes_wiki']) + 1)
                    
                    cache_timouts['usernotes_wiki'] = time.time()

                    usernotes = bot.r.get_wiki_page(subreddit, 'usernotes')
                    unesc_usernotes = parser.unescape(usernotes.content_md)
                    json_notes = json.loads(unesc_usernotes)

                    moderators = json_notes['constants']['users']
                    warnings = json_notes['constants']['warnings']

                    bot_reply = ''

                    try: #Usernotes
                        notes = json_notes['users'][command[1]]['ns']

                        bot_reply += '**User Report: ' + command[1] + '**\n---\n\nWarning | Reason | Moderator\n---|---|----\n'

                        for note in notes:
                            bot_reply += warnings[note['w']] + ' | ' + note['n'] + ' | ' + moderators[note['m']] + '\n'
                    except KeyError:
                        print('[' + eval(bot.ts) + '] Could not find user ' + command[1] + ' in usernotes')

                    content = []

                    try: #Shadowban/whitelist check
                        if (time.time() - cache_timouts['automoderator_wiki']) < bot.r.config.cache_timeout + 1:
                            time.sleep(int(time.time() - cache_timouts['automoderator_wiki']) + 1)
                        
                        cache_timouts['automoderator_wiki'] = time.time()

                        automod_config = bot.r.get_wiki_page(subreddit, 'automoderator')
                        unesc_wiki = parser.unescape(automod_config.content_md)

                        wiki_lines = unesc_wiki.split('\n')

                        shadowban_line = wiki_lines.index('    #$ELI5BOT$ SHADOWBANS') + 1
                        shadowbans = wiki_lines[shadowban_line]

                        user_pattern = re.compile(ur'([-_A-Za-z0-9]{3,20})[,\]]')
                        usernames = re.findall(user_pattern, shadowbans)

                        if lower(command[1]) in [x.lower() for x in usernames]:
                            bot_reply += '**Shadowbanned**: True\n\n'
                        else:
                            bot_reply += '**Shadowbanned**: False\n\n'

                        whitelist_line = wiki_lines.index('    #$ELI5BOT$ WHITELIST') + 2
                        whitelists = wiki_lines[shadowban_line]

                        usernames = re.findall(user_pattern, whitelists)

                        if lower(command[1]) in [x.lower() for x in usernames]:
                            bot_reply += '**Troll Whitelisted**: True\n\n'
                        else:
                            bot_reply += '**Troll Whitelisted**: False\n\n'

                    except ValueError:
                        printlog('Malformed AutoMod wiki (shadowbans/whitelist)')

                    try: #Comments and submissions
                        user = bot.r.get_redditor(command[1])

                        for comment in user.get_comments(limit=100):
                            if comment.subreddit == subreddit:
                                content.append(comment)

                            if len(content) > 30:
                                break

                        for submitted in user.get_submitted(limit=20):
                            if submitted.subreddit == subreddit:
                                content.append(submitted)                        

                        content.sort(key=lambda x: x.score, reverse=False)

                        #Cut down to bottom 10 content
                        while len(content) > 12:
                            del content[12]

                        deltaT = int(time.time() - user.created_utc)

                        bot_reply += '\n\n[**/u/' + command[1] + '**](http://reddit.com/user/' + command[1] + ') - Age: ' + str(datetime.timedelta(0, deltaT)) + '\n\n'
                        bot_reply += 'Link | Body/Title | Score\n---|---|----\n'

                        for content_object in content:
                            if type(content_object) == praw.objects.Comment:
                                temp_comment = content_object.body.replace('\n', ' ')

                                #Cut down comments to 200 characters, while extending over the 200 char limit
                                #to preserve markdown links
                                if len(temp_comment) > 200:
                                    i = 200
                                    increment = -1

                                    link = False

                                    while i > -1 and (i + 1) < len(temp_comment):
                                        if temp_comment[i] == ')':
                                            link = True
                                            break

                                        if temp_comment[i] == '(':
                                            if temp_comment[i - 1] == ']':
                                                increment = 1
                                            else:
                                                break

                                        i += increment

                                    i += 1
                                    
                                    if i < 200 or link == False:
                                        i = 200

                                    temp_comment = temp_comment[:i]

                                    if i >= len(temp_comment):
                                        temp_comment += '...'

                                if content_object.banned_by == None:
                                    bot_reply += '[Comment](' + content_object.permalink + '?context=3) | ' + temp_comment + ' | ' + str(content_object.score) + '\n'
                                else:
                                    bot_reply += '[**Comment**](' + content_object.permalink + '?context=3) | ' + temp_comment + ' | ' + str(content_object.score) + '\n'

                            if type(content_object) == praw.objects.Submission:
                                if content_object.banned_by == None:
                                    bot_reply += '[Submission](' + content_object.permalink + ') | ' + content_object.title + ' | ' + str(content_object.score) + '\n'
                                else:
                                    bot_reply += '[**Submission**](' + content_object.permalink + ') | ' + content_object.title + ' | ' + str(content_object.score) + '\n'

                    except:
                        printlog('Error while trying to read user comments')

                    message.reply(bot_reply)
                    print('[' + eval(bot.ts) + '] Summary on ' + command[1] + ' provided')

                except Exception,e:
                    message.reply('**Error**:\n\nError while providing summary')
                    printlog('Error while trying to give summary on ' + command[1] + ': ' + str(e))

            else:
                message.reply('**Syntax Error**:\n\n    !Summary username')

        else:
            message.reply('**Unknown Command:**\n\n    !' + command[0])

        #End of command parsing

    if len(automod_jobs[0]) > 0: #If necessary apply all recent changes to automoderator configuration page
        if (time.time() - cache_timouts['automoderator_wiki']) < bot.r.config.cache_timeout + 1:
            time.sleep(int(time.time() - cache_timouts['automoderator_wiki']))
        
        cache_timouts['automoderator_wiki'] = time.time()

        automod_config = bot.r.get_wiki_page(subreddit, 'automoderator')
        new_content = parser.unescape(automod_config.content_md)

        for x in range(len(automod_jobs[0])):
            if automod_jobs[0][x] == 'shadowban':
                new_content = new_content.replace('do_not_remove', 'do_not_remove, ' + automod_jobs[1][x])

            elif automod_jobs[0][x] == 'lock':
                new_content = new_content.replace('do_not_touch', 'do_not_touch, ' + automod_jobs[1][x])

        try:
            if len(automod_jobs[0]) == 1:
                if automod_jobs[0][0] == 'shadowban':
                    reason = str(message.author) + ': Shadowbanning ' + automod_jobs[1][0] + ' for ' + shadowban_reason

                elif automod_jobs[0][0] == 'lock':
                    reason = str(message.author) + ': Locking ' + automod_jobs[1][0]

            else:
                reason = str(message.author) + ': Multiple reasons'

            bot.r.edit_wiki_page(subreddit, 'automoderator', new_content, reason)
            bot.r.send_message('AutoModerator', subreddit.display_name, 'update')

            message_backlog.append(message)

            printlog('Updated AutoModerator wiki page')

        except Exception,e:
            printlog('Error while updating AutoModerator wiki page: ' + str(e))

    if len(usernotes_jobs[0]) > 0:
        if (time.time() - cache_timouts['usernotes_wiki']) < bot.r.config.cache_timeout + 1:
            time.sleep(int(time.time() - cache_timouts['usernotes_wiki']))
        
        cache_timouts['usernotes_wiki'] = time.time()

        usernotes_page = bot.r.get_wiki_page(subreddit, 'usernotes')
        content = parser.unescape(usernotes_page.content_md)

        notes = json.loads(content)

        moderators = notes['constants']['users']
        mod_name = message.author.name

        try:
            mod_index = moderators.index(mod_name)
        except ValueError:
            notes['constants']['users'].append(mod_name)
            mod_index = moderators.index(mod_name)

        for x in range(len(usernotes_jobs[0])):
            try:
                username = bot.r.get_redditor(usernotes_jobs[0][x]).name
            except:
                username = usernotes_jobs[0][x]

            if usernotes_jobs[1][x] == '':
                reason = 'Shadowbanned'
            else:
                reason = 'Shadowbanned for ' + usernotes_jobs[1][x]

            time_of_ban = int(1000*time.time())

            new_JSON_object = json.loads('{"n":"' + reason + '","t":' + str(time_of_ban) + ',"m":' + str(mod_index) + ',"l":"","w":1}')

            try:
                notes['users'][username]['ns'].insert(0, new_JSON_object)
            except KeyError:
                notes['users'][username] = {}
                notes['users'][username]['ns'] = []
                notes['users'][username]['ns'].append(new_JSON_object)

        if len(usernotes_jobs[0]) == 1:
            edit_reason = message.author.name + ': "create new note on ' + usernotes_jobs[0][x] + '" via ' + bot.username
        else:
            edit_reason = message.author.name + ': "create new note on multiple users" via ' + bot.username

        new_content = json.dumps(notes)
        bot.r.edit_wiki_page(subreddit, 'usernotes', new_content, edit_reason)

        printlog('Added shadowban notice to usernotes for ' + username)

def printlog(logmessage):
    logging.info('[' + eval(bot.ts) + '] ' + logmessage)
    print('[' + eval(bot.ts) + '] ' + logmessage)

def main():
    logging.basicConfig(filename='teaBot.log',level=logging.DEBUG)
    
    try:
        #Logs into the reddit account
        bot.r.login(bot.username, bot.password)
        printlog('LittleTeaBot for ' + bot.subreddit + '/' + bot.version + ' started')
    except:
        printlog('[' + eval(bot.ts) + '] Error while trying to log into reddit account')
        sys.exit('Reddit login error')
    
    try:
        #Connects the bot to explainlikeimfive
        subreddit = bot.r.get_subreddit(bot.subreddit)
        
        printlog('Connected to ' + bot.subreddit)
    except:
        printlog('Error while obtaining subreddit information for ' + bot.subreddit)
        sys.exit('Subreddit info fetch error')
    
    while True:
        try:
            check_modmail(subreddit)
        except Exception,e:
            printlog('Error in modmail section: ' + str(e))

        try:
            check_pms(subreddit)
        except Exception,e:
            printlog('Error in PM section: ' + str(e))

        time.sleep(1)

    
if __name__ == '__main__':
    main()
