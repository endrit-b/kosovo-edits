import json
import tweepy
import ConfigParser
import urllib2
import logging
from urllib import urlencode
from time import sleep

# creating config objects
config = ConfigParser.RawConfigParser()
config.read('config.cfg')

# getting twitter properties
TWITTER_API_KEY = config.get('Twitter', 'API_KEY')
TWITTER_API_SECRET = config.get('Twitter', 'API_SECRET')
TWITTER_ACCESS_TOKEN = config.get('Twitter', 'ACCESS_TOKEN')
TWITTER_ACCESS_TOKEN_SECRET = config.get('Twitter', 'ACCESS_TOKEN_SECRET')

# creating twitter api object
auth = tweepy.OAuthHandler(TWITTER_API_KEY, TWITTER_API_SECRET)
auth.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET)
api = tweepy.API(auth)

# getting bitly properties
BITLY_USERNAME = config.get('Bitly', 'USERNAME')
BITLY_API_KEY = config.get('Bitly', 'API_KEY')

# Getting the application properties
SLEEP_TIME = config.get('Application', 'SLEEP_TIME')
REVISION_TRACKER_FILENAME = config.get('Application', 'REVISION_TRACKER_FILENAME')
WIKIPEDIA_PAGE_IDS = config.get('Application', 'WIKIPEDIA_PAGE_IDS')

# Logging path might be relative or starts from the root.
# If it's relative then be sure to prepend the path with the application's root directory path.
LOG_PATH = config.get('Logging', 'PATH')
LOG_LEVEL = config.get('Logging', 'LEVEL').upper()
logging.basicConfig(filename=LOG_PATH, level=LOG_LEVEL)

revision_tracker_config = ConfigParser.RawConfigParser()
revision_tracker_config.read(REVISION_TRACKER_FILENAME)


def run():
    ''' The main program function.
    '''

    # Build a list of monitored page ids:
    page_ids = WIKIPEDIA_PAGE_IDS.split('|')

    # Build the GET request URL to hit Wikipedia's API
    wikipedia_latest_revision_api_request_url = 'http://en.wikipedia.org/w/api.php?action=query&prop=revisions&pageids=%s&rvprop=timestamp|ids|user|comment&format=json' % WIKIPEDIA_PAGE_IDS

    # Get the response from Wikipidia's API
    response = urllib2.urlopen(wikipedia_latest_revision_api_request_url)
    json_response = json.load(response)

    # Iterate through the revision info of every page listed in the response
    for page_id in page_ids:

        # Get the title.
        title = json_response['query']['pages'][page_id]['title']

        # Get the revisions.
        revisions = json_response['query']['pages'][page_id]['revisions']

        # For now, we will only check the latest revision.
        # We'll make the polling occur at a high enough frequency that will minimize the risks of missing a revision.
        #
        # TODO: Check older revisions as well to make sure we didn't miss any: this will happen if more than one
        # revision is submitted between two requests to Wikipedia's API (unlikely to occur, but Murphy's Law!).
        latest_revision = revisions[0]

        # Only process this revision if we haven't done so already in our last request.
        # In other words, let's not attempt to make duplicate tweets.
        if is_new_revision(page_id, latest_revision):

            # Build revision url. e.g. http://en.wikipedia.org/w/index.php?title=Kosovo&diff=619399922&oldid=619329366
            url = build_wikipedia_revision_url(title, latest_revision)

            # Requesting bitly shortened url of revision url
            shortened_url = shorten_url(url)

            # building the twitter message
            user = latest_revision['user']
            twitter_message = "%s edited the '%s' article: %s" % (user, title, shortened_url)

            logging.info(twitter_message)

            # tweet message
            api.update_status(twitter_message)

            # Store the current revision number as the previous revision number.
            # We do this to check if the next revision we will pull won't be the same one as this one.
            # In other words, we will want to check if no new edits were made since the last request.
            # If no new edits were made since the last request, then we won't tweet anything.
            store_latest_revision_id(page_id, latest_revision)


def build_wikipedia_revision_url(article_title, revision):
    ''' Build the wikipedia revision diff URL.
    :param article_title: The title of the article.
    :param revision: The revision.
    '''
    rev_id = revision['revid']
    parent_id = revision['parentid']

    url = "http://en.wikipedia.org/w/index.php?title=%s&diff=%d&oldid=%d" % (article_title, rev_id, parent_id)

    return url


def shorten_url(url):
    ''' Uses Bitly API to shorten a given url.
    :param url: The url to shorten.
    '''

    # Make the request to the API.
    params = urlencode({'longUrl': url, 'login':BITLY_USERNAME, 'apiKey':BITLY_API_KEY, 'format': 'json'})
    req = urllib2.Request("http://api.bit.ly/v3/shorten?%s" % params)

    # Process the response.
    response_bitly = urllib2.urlopen(req)
    response_bitly_json = json.load(response_bitly)

    shortened_url = response_bitly_json['data']['url']

    return shortened_url


def is_new_revision(page_id, revision):
    ''' Checks if the given revision is a new one.
    :param revision: The revision object.
    '''

    # The current revision for the given page
    current_revision_id = int(revision['revid'])

    # Get revision processed for the same page but in the previous loop
    previous_revision_id = int(revision_tracker_config.get('Revisions', str(page_id)))

    # Check if current and previous revision are the same
    current_revision_is_a_new_revision = current_revision_id != previous_revision_id

    return current_revision_is_a_new_revision


def store_latest_revision_id(page_id, revision):
    ''' Store the last revision number.
    :param page_id: the page id.
    :param revision: The lastest revision.
    '''

    # Get latest revision id.
    latest_revision_id = revision['revid']

    # Updated config object
    revision_tracker_config.set('Revisions', str(page_id), str(latest_revision_id))

    # Write update in file
    with open(REVISION_TRACKER_FILENAME, 'wb') as configfile:
        revision_tracker_config.write(configfile)



logging.info("Application started.")
logging.info("Observing the following pages: " + WIKIPEDIA_PAGE_IDS.replace('|', ', '))

# Infinite application loop, commence!
while True:
    try:
        run()
    except:
        logging.exception("An error occured wile polling for changes.")

    # Wait for a bit before checking if there are any new edits.
    # But not too much that we would risk missing an edits (because we only look at the latest edit for now)
    sleep(float(SLEEP_TIME))
