#!/usr/bin/python2.5
#
# Copyright 2008 Google Inc.
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

"""Result ranker Unit Tests."""

__author__ = 'slamm@google.com (Stephen Lamm)'

import logging
import unittest

from google.appengine.api import datastore
from google.appengine.api import datastore_errors
from google.appengine.api import memcache
from categories import test_set_base
from models import result_ranker

import mock_data

MockTestSet = mock_data.MockTestSet

class CountRankerTest(unittest.TestCase):
  def setUp(self):
    self.test_set = MockTestSet()
    self.ranker_params = (self.test_set.tests[1], 'Android 0.5')
    self.ranker = result_ranker.GetOrCreateRanker(*self.ranker_params)

  def tearDown(self):
    self.ranker.delete()

  def testAddScore(self):
    ranker = result_ranker.GetRanker(*self.ranker_params)
    ranker.Add(2)
    ranker = result_ranker.GetRanker(*self.ranker_params)
    self.assertEqual([0, 0, 1], ranker.counts)
    self.assertEqual((2, 1), ranker.GetMedianAndNumScores())
    ranker.Add(4)
    ranker = result_ranker.GetRanker(*self.ranker_params)
    self.assertEqual([0, 0, 1, 0, 1], ranker.counts)
    self.assertEqual((4, 2), ranker.GetMedianAndNumScores())
    ranker.Add(2)
    ranker = result_ranker.GetRanker(*self.ranker_params)
    self.assertEqual([0, 0, 2, 0, 1], ranker.counts)
    self.assertEqual((2, 3), ranker.GetMedianAndNumScores())

  def testSetCounts(self):
    ranker = result_ranker.GetRanker(*self.ranker_params)
    ranker.SetCounts([0, 3, 1, 3])
    ranker = result_ranker.GetRanker(*self.ranker_params)
    self.assertEqual((2, 7), ranker.GetMedianAndNumScores())
    ranker.SetCounts([4, 3])
    ranker = result_ranker.GetRanker(*self.ranker_params)
    self.assertEqual((0, 7), ranker.GetMedianAndNumScores())
    ranker.Add(1)
    ranker = result_ranker.GetRanker(*self.ranker_params)
    self.assertEqual((1, 8), ranker.GetMedianAndNumScores())

  def testAddScoreTooBig(self):
    ranker = result_ranker.GetRanker(*self.ranker_params)
    ranker.Add(101)
    ranker = result_ranker.GetRanker(*self.ranker_params)
    self.assertEqual((100, 1), ranker.GetMedianAndNumScores())

  def testAddScoreTooSmall(self):
    ranker = result_ranker.GetRanker(*self.ranker_params)
    ranker.Add(-1)
    ranker = result_ranker.GetRanker(*self.ranker_params)
    self.assertEqual((0, 1), ranker.GetMedianAndNumScores())


class LastNRankerTest(unittest.TestCase):
  def setUp(self):
    self.test_set = MockTestSet()
    self.ranker_params = (self.test_set.tests[2], 'Safari 4.1')
    self.ranker = result_ranker.GetOrCreateRanker(*self.ranker_params)
    self.old_max_num_scores = result_ranker.LastNRanker.MAX_NUM_SAMPLED_SCORES

  def tearDown(self):
    self.ranker.delete()
    result_ranker.LastNRanker.MAX_NUM_SAMPLED_SCORES = self.old_max_num_scores

  def testAddScore(self):
    ranker = result_ranker.GetRanker(*self.ranker_params)
    ranker.Add(1000)
    ranker = result_ranker.GetRanker(*self.ranker_params)
    self.assertEqual([1000], ranker.scores)
    self.assertEqual((1000, 1), ranker.GetMedianAndNumScores())

    ranker.Add(0)
    ranker = result_ranker.GetRanker(*self.ranker_params)
    self.assertEqual([0, 1000], ranker.scores)
    self.assertEqual((1000, 2), ranker.GetMedianAndNumScores())
    ranker.Add(500)
    ranker = result_ranker.GetRanker(*self.ranker_params)
    self.assertEqual([0, 500, 1000], ranker.scores)
    self.assertEqual((500, 3), ranker.GetMedianAndNumScores())

  def testSetScores(self):
    ranker = result_ranker.GetRanker(*self.ranker_params)
    ranker.SetScores([4, 4, 5, 5, 6], 10)
    ranker = result_ranker.GetRanker(*self.ranker_params)
    self.assertEqual((5, 10), ranker.GetMedianAndNumScores())
    ranker.Add(4)
    ranker = result_ranker.GetRanker(*self.ranker_params)
    self.assertEqual((5, 11), ranker.GetMedianAndNumScores())
    ranker.Add(4)
    ranker = result_ranker.GetRanker(*self.ranker_params)
    self.assertEqual([4, 4, 4, 4, 5, 5, 6], ranker.scores)
    self.assertEqual((4, 12), ranker.GetMedianAndNumScores())

  def testDropLowScore(self):
    result_ranker.LastNRanker.MAX_NUM_SAMPLED_SCORES = 5
    ranker = result_ranker.GetRanker(*self.ranker_params)
    ranker.SetScores([4, 4, 5, 5, 6], 15)
    ranker.Add(5)
    ranker = result_ranker.GetRanker(*self.ranker_params)
    self.assertEqual([4, 5, 5, 5, 6], ranker.scores)
    self.assertEqual((5, 16), ranker.GetMedianAndNumScores())

  def testDropHighScore(self):
    result_ranker.LastNRanker.MAX_NUM_SAMPLED_SCORES = 4
    ranker = result_ranker.GetRanker(*self.ranker_params)
    ranker.SetScores([4, 4, 5, 5], 20)
    ranker.Add(4)
    ranker = result_ranker.GetRanker(*self.ranker_params)
    self.assertEqual([4, 4, 4, 5], ranker.scores)
    self.assertEqual((4, 21), ranker.GetMedianAndNumScores())