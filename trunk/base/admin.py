#!/usr/bin/python2.5
#
# Copyright 2009 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the 'License')
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Handlers administrative tasks.

Confirm new user agents.
- Change their browser designation, if needed.
- Delete tests (e.g. spam).
"""

__author__ = 'slamm@google.com (Stephen Lamm)'

import datetime
import logging
import os
import time
import traceback
import urllib

from google.appengine.api.labs import taskqueue
from google.appengine.ext import db

import settings
from categories import all_test_sets
from base import decorators
from base import manage_dirty
from base import util
from models import result_stats
from models.result import ResultParent
from models.result import ResultTime
from models.user_agent import UserAgent
#from models.user_agent import UserAgentGroup

from django import http
from django.utils import simplejson
from third_party.gaefy.db import pager

from django.template import add_to_builtins
add_to_builtins('base.custom_filters')


UPDATE_ALL_BATCH_SIZE = 25
UPDATE_ALL_UNCACHED_BATCH_SIZE = 250


def Render(request, template_file, params):
  """Render network test pages."""

  return util.Render(request, template_file, params)

@decorators.admin_required
def Admin(request):
  """Admin Tools"""

  params = {
    'page_title': 'Admin Tools',
    'application_id': os.environ['APPLICATION_ID'],
    'current_version_id': os.environ['CURRENT_VERSION_ID'],
    'is_development': settings.BUILD == 'development',
    'is_paused': manage_dirty.UpdateDirtyController.IsPaused(),
  }
  return Render(request, 'admin/admin.html', params)


@decorators.admin_required
def GetDirty(request):
  category = request.GET.get('category')
  dirty = request.GET.get('dirty', '1')
  is_dirty = False
  if dirty == '1':
    is_dirty = True

  parents = db.Query(ResultParent)
  parents.filter('category =', category)

  dirtys = []
  for parent in parents:
    logging.info('parent %s' % parent.key())
    time = db.Query(ResultTime)
    if is_dirty:
      time.filter('dirty =', True)
    time.ancestor(parent)
    logging.info('time.count() %s' % time.count())
    if time.count() > 0:
      key = parent.key()
      dirtys.append(
          '<a href="/admin/schedule-dirty-update?result_parent_key=%s">'
          'Dirty ResultParent: %s. %s</a>' % (key, parent.user_agent.pretty(),
                                              key))

  return http.HttpResponse('<br>'.join(dirtys))


@decorators.admin_required
def ScheduleDirtyUpdate(request):
  result_parent_key = request.GET.get('result_parent_key')
  ResultParent.ScheduleDirtyUpdate(result_parent_key)
  return http.HttpResponse('Ok, ScheduleDirtyUpdate for %s' % result_parent_key)


@decorators.check_csrf
def SubmitChanges(request):
  logging.info('^^^^^^^^^^^^^^^^^^^^ SubmitChanges')
  encoded_ua_keys = [key[3:] for key in request.GET if key.startswith('ac_')]
  logging.info('Encoded ua keys: %s' % ', '.join(encoded_ua_keys))
  update_user_agents = []
  for encoded_key in encoded_ua_keys:
    action = request.REQUEST['ac_%s' % encoded_key]
    ua = db.get(db.Key(encoded=encoded_key))
    if action == 'confirm' and not ua.confirmed:
      ua.confirmed = True
      update_user_agents.append(ua)
    if action == 'unconfirm' and ua.confirmed:
      ua.confirmed = False
      update_user_agents.append(ua)
    if action == 'change' and not ua.changed:
      change_to = request.REQUEST['cht_%s' % key]
      if change_to != ua.pretty():
        #UserAgent.parse_to_string_list(change_to)
        #ua.family =
        pass
  logging.info('Update user agents: %s' % ', '.join([ua.string for ua in update_user_agents]))
  db.put(update_user_agents)
  return http.HttpResponse('Time to go to the next page.')


@decorators.admin_required
@decorators.provide_csrf
def ConfirmUa(request):
  """Confirm User-Agents"""

  search_browser = request.REQUEST.get('browser', '')
  search_unconfirmed = request.REQUEST.get('unconfirmed', True)
  search_confirmed = request.REQUEST.get('confirmed', False)
  search_changed = request.REQUEST.get('changed', False)

  if 'search' in request.REQUEST:
    pass
  elif 'submit' in request.REQUEST:
    return SubmitChanges(request)

  user_agents = UserAgent.all().order('string').fetch(1000)
  user_agents = user_agents[:10]

  for ua in user_agents:
    match_spans = UserAgent.MatchSpans(ua.string)
    ua.match_strings = []
    last_pos = 0
    for start, end in match_spans:
      if start > last_pos:
        ua.match_strings.append((False, ua.string[last_pos:start]))
      ua.match_strings.append((True, ua.string[start:end]))
      last_pos = end
    if len(ua.string) > last_pos:
      ua.match_strings.append((False, ua.string[last_pos:]))

  params = {
    'page_title': 'Confirm User-Agents',
    'user_agents': user_agents,
    'search_browser': search_browser,
    'search_unconfirmed': search_unconfirmed,
    'search_confirmed': search_confirmed,
    'search_changed': search_changed,
    'csrf_token': request.session['csrf_token'],
    'use_parse_service': False,
  }
  return Render(request, 'admin/confirm-ua.html', params)


@decorators.admin_required
def Stats(request):
  """Stats"""

  params = {
    'page_title': 'Stats',
  }
  return util.Render(request, 'admin/stats.html', params)


@decorators.admin_required
def DataDump(request):
  """This is used by bin/data_dump.py to replicate the datastore."""
  model = request.REQUEST.get('model')
  key_prefix = request.REQUEST.get('key_prefix', '')
  keys_list = request.REQUEST.get('keys')
  time_limit = int(request.REQUEST.get('time_limit', 3))

  if keys_list:
    keys = ['%s%s' % (key_prefix, key) for key in keys_list.split(',')]
  else:
    return http.HttpResponseBadRequest('"keys" is a required parameter.')

  start_time = datetime.datetime.now()

  if model == 'ResultParent':
    query = pager.PagerQuery(ResultParent, keys_only=True)
  elif model == 'UserAgent':
    query = pager.PagerQuery(UserAgent)
  else:
    return http.HttpResponseBadRequest(
        'model must be one of "ResultParent", "UserAgent".')
  data = []
  error = None
  if model == 'ResultParent':
    result_time_query = ResultTime.gql('WHERE ANCESTOR IS :1')
    for result_parent_key in keys:
      if (datetime.datetime.now() - start_time).seconds > time_limit:
        error = 'Over time limit'
        break
      try:
        p = ResultParent.get(result_parent_key)
      except db.Timeout:
        error = 'db.Timeout: ResultParent'
        break
      if not p:
        data.append({
          'model_class': 'ResultParent',
          'lost_key': result_parent_key,
          })
        continue
      result_time_query.bind(p.key())
      try:
        result_times = result_time_query.fetch(1000)
      except db.Timeout:
        error = 'db.Timeout: ResultTime'
        break
      row_data = [{
          'model_class': 'ResultParent',
          'result_parent_key': result_parent_key,
          'category': p.category,
          'user_agent_key': str(
              ResultParent.user_agent.get_value_for_datastore(p)),
          'ip': p.ip,
          'user_id': p.user and p.user.user_id() or None,
          'created': p.created and p.created.isoformat() or None,
          'params_str': p.params_str,
          'loader_id': hasattr(p, 'loader_id') and p.loader_id or None,
          }]
      is_dirty = False
      for result_time in result_times:
        if result_time.dirty:
          is_dirty = True
          break
        row_data.append({
            'model_class': 'ResultTime',
            'result_time_key': str(result_time.key()),
            'result_parent_key': str(result_parent_key),
            'test': result_time.test,
            'score': result_time.score,
            })
      if is_dirty:
        data.append({'dirty_key': result_parent_key,})
      else:
        data.extend(row_data)
  elif model == 'UserAgent':
    try:
      user_agents = UserAgent.get(keys)
    except db.Timeout:
      error = 'db.Timeout: UserAgent'
    else:
      for key, ua in zip(keys, user_agents):
        if ua:
          data.append({
              'model_class': 'UserAgent',
              'user_agent_key': key,
              'string': ua.string,
              'family': ua.family,
              'v1': ua.v1,
              'v2': ua.v2,
              'v3': ua.v3,
              'confirmed': ua.confirmed,
              'created': ua.created and ua.created.isoformat() or None,
              'js_user_agent_string': (hasattr(ua, 'js_user_agent_string') and
                                       ua.js_user_agent_string or None),
              })
        else:
          data.append({
              'model_class': 'UserAgent',
              'lost_key': key,
              })
  response_params = {
      'data': data,
      }
  if error:
    response_params['error'] = error
  return http.HttpResponse(content=simplejson.dumps(response_params),
                           content_type='application/json')


@decorators.admin_required
def DataDumpKeys(request):
  """This is used by bin/data_dump.py to get ResultParent keys."""
  bookmark = request.REQUEST.get('bookmark')
  model_name = request.REQUEST.get('model')
  count = int(request.REQUEST.get('count', 0))
  fetch_limit = int(request.REQUEST.get('fetch_limit', 999))
  created_str = request.REQUEST.get('created', 0)
  created = None
  if created_str:
    created = datetime.datetime.strptime(created_str, '%Y-%m-%d %H:%M:%S')
  models = {
      'UserAgent': UserAgent,
      'ResultParent': ResultParent,
      'ResultTime': ResultTime,
      }
  model = models.get(model_name, UserAgent)
  query = pager.PagerQuery(model, keys_only=True)
  if created:
    query.filter('created >=', created)
    query.order('created')
  try:
    prev_bookmark, results, next_bookmark = query.fetch(fetch_limit, bookmark)
  except db.Timeout:
    logging.warn('db.Timeout during initial fetch.')
    return http.HttpResponseServerError('db.Timeout during initial fetch.')
  response_params = {
      'bookmark': next_bookmark,
      'model': model_name,
      'count': count + len(results),
      'keys': [str(key) for key in results]
      }
  if created_str:
    response_params['created'] = created_str
  return http.HttpResponse(content=simplejson.dumps(response_params),
                           content_type='application/json')

@decorators.admin_required
def UploadCategoryBrowsers(request):
  """Upload browser lists for each category and version level."""
  category = request.REQUEST.get('category')
  version_level = request.REQUEST.get('version_level')
  browsers_str = request.REQUEST.get('browsers')

  if not category:
    return http.HttpResponseServerError(
        'Must set "category".')
  if not version_level.isdigit() or int(version_level) not in range(4):
    return http.HttpResponseServerError(
        'Version level must be an integer 0..3.')
  if not browsers_str:
    return http.HttpResponseServerError(
        'Must set "browsers" (comma-separated list).')

  version_level = int(version_level)
  browsers = browsers_str.split(',')
  result_stats.CategoryBrowserManager.SetBrowsers(
      category, version_level, browsers)
  UpdateSummaryBrowsers(request)
  return http.HttpResponse('Success.')


def UpdateCategory(request):
  category = request.REQUEST.get('category')
  user_agent_key = request.REQUEST.get('user_agent_key')
  if not category:
    logging.info('cron.UserAgentGroup: No category')
    return http.HttpResponse('No category')
  if not all_test_sets.GetTestSet(category):
    logging.info('cron.UserAgentGroup: Bad category: %s', category)
    return http.HttpResponse('Bad category: %s' % category)
  if not user_agent_key:
    logging.info('cron.UserAgentGroup: No key')
    return http.HttpResponse('No key')
  try:
    user_agent = UserAgent.get(db.Key(user_agent_key))
  except db.BadKeyError:
    logging.info('cron.UserAgentGroup: Invalid UserAgent key: %s', user_agent_key)
    return http.HttpResponse('Invalid UserAgent key: %s' % user_agent_key)
  if user_agent:
    logging.info('cron.UserAgentGroup: UpdateCategory(%s, %s)', category, user_agent)
    result_stats.UpdateCategory(category, user_agent)
    return http.HttpResponse('Done with UserAgent key=%s' % user_agent_key)
  else:
    return http.HttpResponse('No user_agent with this key.')


@decorators.admin_required
def UpdateSummaryBrowsers(request):
  """Update all the browsers for the summary category."""
  result_stats.CategoryBrowserManager.UpdateSummaryBrowsers(
      [ts.category for ts in all_test_sets.GetVisibleTestSets()])
  return http.HttpResponse('Success.')


def UpdateStatsCache(request):
  """Load rankers into memcache."""
  category = request.REQUEST.get('category')
  browsers_str = request.REQUEST.get('browsers')
  is_uncached_update = request.REQUEST.get('is_uncached_update')
  if not category:
    logging.info('UpdateStatsCache: Must set category')
    return http.HttpResponseServerError('Must set "category".')
  logging.info('UpdateStatsCache: category=%s, browsers=%s',
               category, browsers_str)
  if not browsers_str:
    logging.info('UpdateStatsCache: Must set "browsers".')
    return http.HttpResponseServerError('Must set "browsers".')
  browsers = browsers_str.split(',')
  if is_uncached_update:
    num_checked_browsers = len(browsers)
    browsers = result_stats.CategoryStatsManager.FindUncachedStats(
        category, browsers)
    logging.debug('Uncached \'%s\' stats (count: %s out of %s): %s',
                  category, len(browsers), num_checked_browsers, browsers)
  # Only process one browser in each task.
  if len(browsers) > 1:
    taskqueue.Task(params={
        'category': category,
        'browsers': ','.join(browsers[1:]),
        }).add(queue_name='update-stats-cache')
  result_stats.CategoryStatsManager.UpdateStatsCache(category, browsers[:1])
  return http.HttpResponse('Success.')


def UpdateAllStatsCache(request, batch_size=UPDATE_ALL_BATCH_SIZE,
                        is_uncached_update=False):
  categories_str = request.REQUEST.get('categories')
  if categories_str:
    categories = categories_str.split(',')
  else:
    categories = [s.category for s in  all_test_sets.GetVisibleTestSets()]
  if not categories:
    return http.HttpResponseServerError('No categories given.')
  elif len(categories) > 1:
    for category in categories:
      task = taskqueue.Task(url=request.path, params={'categories': category})
      task.add(queue_name='update-stats-cache')
    return http.HttpResponse('Queued stats cache update for categories: %s' %
                             categories)
  category = categories[0]
  test_set = all_test_sets.GetTestSet(category)
  browsers = result_stats.CategoryBrowserManager.GetAllBrowsers(category)
  logging.info('Update all stats cache: %s', category)
  for i in range(0, len(browsers), batch_size):
    params={
        'category': category,
        'browsers': ','.join(browsers[i:i+batch_size]),
        }
    if is_uncached_update:
      params['is_uncached_update'] = 1
    taskqueue.Task(params=params).add(queue_name='update-stats-cache')
    logging.info('Added task for browsers %s to %s.', i, i+batch_size)
  return http.HttpResponse('Done creating update tasks.')


def UpdateAllUncachedStats(request, batch_size=UPDATE_ALL_UNCACHED_BATCH_SIZE):
  return UpdateAllStatsCache(request, batch_size, is_uncached_update=True)
