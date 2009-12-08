#!/usr/bin/python2.5
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

"""Shared cron handlers."""

__author__ = 'elsigh@google.com (Lindsey Simon)'


from google.appengine.api import memcache
from google.appengine.ext import db

import django
from django import http

from categories import all_test_sets
from models import result_stats
from models.result import ResultParent
from models.user_agent import UserAgent

import util
import settings


def UserAgentGroup(request):
  category = request.REQUEST.get('category')
  user_agent_key = request.REQUEST.get('user_agent_key')
  if not category:
    return http.HttpResponse('No category')
  if (category not in settings.CATEGORIES and
      category not in settings.CATEGORIES_BETA):
    return http.HttpResponse('Bad category: %s' % category)
  if not user_agent_key:
    return http.HttpResponse('No key')
  try:
    user_agent = UserAgent.get(db.Key(user_agent_key))
  except db.BadKeyError:
    return http.HttpResponse('Invalid UserAgent key: %s' % user_agent_key)
  if user_agent:
    result_stats.UpdateCategory(category, user_agent)
    return http.HttpResponse('Done with UserAgent key=%s' % user_agent_key)
  else:
    return http.HttpResponse('No user_agent with this key.')


def UpdateRecentTests(request):
  max_recent_tests = 10
  skip_categories = settings.CATEGORIES_INVISIBLE + settings.CATEGORIES_BETA

  prev_recent_tests = memcache.get(util.RECENT_TESTS_MEMCACHE_KEY)
  prev_result_parent_key = None
  if prev_recent_tests:
    prev_result_parent_key = prev_recent_tests[0]['result_parent_key']

  recent_tests = []
  recent_query = db.Query(ResultParent).order('-created')
  for result_parent in recent_query.fetch(30):
    if (settings.BUILD == 'production' and
        recent_parent.category in skip_categories):
      continue
    if str(result_parent.key()) == prev_result_parent_key:
      num_needed = max_recent_tests - len(recent_tests)
      if num_needed == max_recent_tests:
        return http.HttpResponse('No update needed.')
      else:
        recent_tests.extend(prev_recent_tests[:num_needed])
        break
    recent_scores = result_parent.GetResults()
    test_set = all_test_sets.GetTestSet(result_parent.category)
    recent_stats = test_set.GetStats(recent_scores)
    recent_tests.append({
        'result_parent_key': str(result_parent.key()),
        'category': result_parent.category,
        'created': result_parent.created,
        'user_agent_pretty': result_parent.user_agent.pretty(),
        'score': recent_stats['summary_score'],
        'display': recent_stats['summary_display'],
        })
    if len(recent_tests) >= max_recent_tests:
      break

  memcache.set(util.RECENT_TESTS_MEMCACHE_KEY, recent_tests,
               time=settings.STATS_MEMCACHE_TIMEOUT)
  return http.HttpResponse('Done')