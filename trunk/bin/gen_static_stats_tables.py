#!/usr/bin/python
#
# Copyright 2009 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Generates static stats tables HTML files."""

_author__ = 'elsigh@google.com (Lindsey Simon)'

import getopt
import logging
import os
import sys
import urllib2

sys.path.extend(['..', '../../..'])
import settings

HOST = 'loadtest.latest.ua-profiler.appspot.com'

# Switches for this script.
# c = categories
# v = version_level
CLI_OPTS = ['c=',
            'v=']

logging.getLogger().setLevel(logging.INFO)
logging.debug('categories: %s' % settings.CATEGORIES)

def main(argv):
  try:
    opts, args = getopt.getopt(argv, 'hg:d', CLI_OPTS)
  except getopt.GetoptError:
    print 'Cannot parse your flags.'
    sys.exit(2)

  # Defaults to do everything.
  categories = settings.CATEGORIES
  version_levels = ['top', '0', '1', '2', '3']

  # Parse the arguments.
  for opt, arg in opts:
    if opt == '--c':
      categories = arg.split(',')
    elif opt == '--v':
      version_levels = arg.split(',')
  logging.info('Switches processed, now c=%s, v=%s' %
               (categories, version_levels))

  for category in categories:
    for version_level in version_levels:
      url = ('http://%s/?category=%s&v=%s&xhr=1' %
             (HOST, category, version_level))
      # Putting this in a retry-able function so that memcache can happen.
      def get_response_until_200(try_response_count):
        print 'Opening URL: %s' % url
        try:
          response = urllib2.urlopen(url)
        except urllib2.HTTPError, e:
          print ('We gots a %s Error in try #%s, retrying...' %
                 (e.code, try_response_count))
          try_response_count += 1
          get_response_until_200(try_response_count)
        except urllib2.URLError, e:
          print 'Death! We failed to reach a server.'
          print 'Reason: ', e.reason
          sys.exit(0)
        else:
          return response
      response = get_response_until_200(1)

      filename = ('../templates/static_%s_%s.html' %
                  (category, version_level))
      f = open(filename, 'w')
      print 'Opened %s' % filename
      html = response.read()
      f.write(html)
      f.close()
      print 'Done.\n'


if __name__ == '__main__':
  main(sys.argv[1:])