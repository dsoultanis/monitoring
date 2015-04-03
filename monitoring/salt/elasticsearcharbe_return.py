#! -*- coding: utf-8 -*-
'''
Return data to an elasticsearch server for indexing.

:maintainer:    Jurnell Cockhren <jurnell.cockhren@sophicware.com>, Arnold Bechtoldt <mail@arnoldbechtoldt.com>
:maturity:      New
:depends:       `elasticsearch-py <http://elasticsearch-py.readthedocs.org/en/latest/>`_
:platform:      all

To enable this returner the elasticsearch python client must be installed
on the desired minions (all or some subset).

The required configuration is as follows:

.. code-block:: yaml

    elasticsearch:
      host: 'somehost.example.com:9200'
      index: 'salt'
      number_of_shards: 1 (optional)
      number_of_replicas: 0 (optional)

or to specify multiple elasticsearch hosts for resiliency:

.. code-block:: yaml

    elasticsearch:
      host:
        - 'somehost.example.com:9200'
        - 'anotherhost.example.com:9200'
        - 'yetanotherhost.example.com:9200'
      index: 'salt'
      number_of_shards: 1 (optional)
      number_of_replicas: 0 (optional)

The above configuration can be placed in a targeted pillar, minion or
master configurations.

To use the returner per salt call:

.. code-block:: bash

    salt '*' test.ping --return elasticsearch

In order to have the returner apply to all minions:

.. code-block:: yaml

    ext_job_cache: elasticsearch
'''
from __future__ import absolute_import

# Import Python libs
import datetime
import logging
import json

# Import Salt libs
#import salt.utils.jid

__virtualname__ = 'elasticsearcharbe'

log = logging.getLogger(__name__)

# Import third party libs
try:
    import elasticsearch
    logging.getLogger('elasticsearch').setLevel(logging.CRITICAL)
    HAS_ELASTICSEARCH = True
except ImportError:
    HAS_ELASTICSEARCH = False

from salt.ext.six import string_types


def _create_index(client, index, fun):
    '''
    Create empty index
    '''
    client.indices.create(index=index,
                          body={
                              'settings': {
                                  'number_of_shards': __salt__['config.get']('elasticsearch:number_of_shards', 1),
                                  'number_of_replicas': __salt__['config.get']('elasticsearch:number_of_replicas', 0),
                              },
                              'mappings': {
                                  fun: {
                                      'properties': {
                                          '@timestamp': {'type': 'date'},
                                          'success': {'type': 'boolean'},
                                          'id': {'type': 'string',
                                                 "index": "not_analyzed"},
                                          'retcode': {'type': 'integer'},
                                          'fun': {'type': 'string',
                                                  "index": "not_analyzed"},
                                          'jid': {'type': 'string',
                                                  "index": "not_analyzed"}
                                      }
                                  }
                              }
                          },
                          ignore=400)


def __virtual__():
    if HAS_ELASTICSEARCH:
        return __virtualname__
    return False


def _get_instance():
    '''
    Return the elasticsearch instance
    '''

    # Check whether we have a single elasticsearch host string, or a list of host strings
    if isinstance(__salt__['config.get']('elasticsearch:host'), list):
        hosts = __salt__['config.get']('elasticsearch:host')
    else:
        hosts = [__salt__['config.get']('elasticsearch:host', 'http://127.0.0.1:9200')]

    return elasticsearch.Elasticsearch(hosts=hosts)


def returner(ret):
    '''
    Process the return from Salt
    '''
    job_fun = ret['fun']
    job_fun_escaped = job_fun.replace('.', '_')
    job_id = ret['jid']
    job_minion_id = ret['id']
    job_success = True if ret['return'] else False
    index = 'salt-{0}'.format(job_fun_escaped)

    # Determine doc type, set a hardcoded default at the moment # TODO
    doc_type = datetime.date.today().strftime('%Y%m%d%H%M%S%f')

    if not job_success:
        log.debug('Won\'t push new data to Elasticsearch, job with jid {0} failed'.format(job_id))
        return

    es = _get_instance()
    index_exists = __salt__['elasticsearcharbe.index_exists'](index)

    if not index_exists:
        __salt__['elasticsearcharbe.index_create']('{0}-v1'.format(index))
        __salt__['elasticsearcharbe.alias_create']('{0}-v1'.format(index), index)
        #log.warn('Won\'t push new data to Elasticsearch, index \'{0}\' does\'t exist! You need to create it yourself!'.format(index))
        #return

    data = {
        '@timestamp': datetime.datetime.now().isoformat(),
        'result': job_success,
        'minion': job_minion_id,
        'fun': job_fun,
        'jid': job_id,
        'return': ret['return'],
    }
    body = json.dumps(data)

    ret = __salt__['elasticsearcharbe.document_create'](index, doc_type, body)


#def prep_jid(nocache, passed_jid=None):  # pylint: disable=unused-argument
def prep_jid(nocache):  # pylint: disable=unused-argument
    '''
    Do any work necessary to prepare a JID, including sending a custom id
    '''
    #return passed_jid if passed_jid is not None else salt.utils.jid.gen_jid()
    return salt.utils.gen_jid()
