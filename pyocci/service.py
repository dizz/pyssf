# 
# Copyright (C) 2010 Platform Computing
# 
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
# 
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
# 
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
# 
'''
Implementation for an OCCI compliant service.

Created on Nov 10, 2010

@author: tmetsch
'''

from pyocci import registry
from pyocci.backends import Backend
from pyocci.core import Mixin
from pyocci.my_exceptions import NoEntryFoundException, ParsingException
from tornado.web import HTTPError
import tornado.web
import uuid

RESOURCES = {}

class BaseHandler(tornado.web.RequestHandler):
    '''
    Handler derived from an handler in the tornado framework. Extended with some
    convenient routines.
    '''

    # disabling 'Too many public methods' pylint check (tornado's fault)
    # pylint: disable=R0904

    version = 'pyocci OCCI/1.1'

    def extract_http_data(self):
        '''
        Extracts all necessary information from the HTTP envelop. Minimize the
        data which is carried around inside of the service. Also ensures that
        the names are always equal - When deployed in Apache the names of the
        Headers change.
        '''
        heads = {}
        headers = self.request.headers
        if 'Category' in headers:
            heads['Category'] = headers['Category']
        if 'X-Occi-Attribute' in headers:
            heads['X-OCCI-Attribute'] = headers['X-Occi-Attribute']
        if 'X-Occi-Location' in headers:
            heads['X-OCCI-Location'] = headers['X-Occi-Location']
        if self.request.body is not '':
            body = self.request.body.strip()
        else:
            body = ''
        return heads, body

    def get_pyocci_parser(self, content_type):
        '''
        Returns the proper pyocci rendering parser.
        
        @param content_type: Either Content-Type or Accept
        @type content_type: str
        '''
        # find a parser for the data format the client provided...
        try:
            return registry.get_parser(self.request.headers[content_type])
        except KeyError:
            return registry.get_parser(registry.DEFAULT_CONTENT_TYPE)
        except NoEntryFoundException as nefe:
            raise HTTPError(400, log_message = str(nefe))

    def get_error_html(self, code, **kwargs):
        msg = str(code)
        try:
            msg += ' ' + repr(kwargs['exception'].log_message)
        except KeyError:
            pass
        return msg

    def _send_response(self, heads, data):
        '''
        Prepares all information to send a response to the client.
        
        @param heads: Data which should go in the header.
        @type heads: dict
        @param data: The body of the HTTP message.
        @type data: str
        '''
        self._headers['Server'] = self.version
        if heads is not None:
            for item in heads.keys():
                self._headers[item] = heads[item]
        self.write(data)

class ResourceHandler(BaseHandler):
    '''
    Handles basic HTTP operations. To achieve this it will make use of WSGI and
    the web.py framework.
    '''

    # disabling 'Too many public methods' pylint check (tornado's fault)
    # disabling 'Arguments number differs from ...' pylint check 
    #                                               (methods exists twice...)
    # pylint: disable=R0904,W0221

    # XXX: What to do with links when creating a resource?

    def post(self, key):
        headers, body = self.extract_http_data()
        parser = self.get_pyocci_parser('Content-Type')

        if self.request.uri.find('?action=') > -1:
            key = self.request.uri.split('?')[0]
            try:
                entity = RESOURCES.get(key)
                action = parser.to_action(headers, body)
                backend = registry.get_backend(action.kind)
                backend.action(entity, action)
            except (ParsingException, AttributeError) as pse:
                raise HTTPError(400, str(pse))
        else:
            # parse the request
            entity = None
            try:
                entity = parser.to_entity(headers, body)
                backend = registry.get_backend(entity.kind)
                backend.create(entity)
            except (ParsingException, AttributeError) as pse:
                raise HTTPError(400, str(pse))

            key = self._create_key(entity)
            RESOURCES[key] = entity
            self._headers['Location'] = key
        self.write('OK')

    def put(self, key):
        headers, body = self.extract_http_data()
        parser = self.get_pyocci_parser('Content-Type')

        if key in RESOURCES.keys():
            old_entity = RESOURCES[key]
            new_entity = None
            try:
                new_entity = parser.to_entity(headers, body,
                                              allow_incomplete = True,
                                              defined_kind = old_entity.kind)

                backend = registry.get_backend(old_entity.kind)
                backend.update(old_entity, new_entity)
            except (ParsingException, AttributeError) as pse:
                raise HTTPError(400, str(pse))
        else:
            try:
                new_entity = parser.to_entity(headers, body)

                backend = registry.get_backend(new_entity.kind)
                backend.create(new_entity)
            except (ParsingException, AttributeError) as pse:
                raise HTTPError(400, str(pse))
            RESOURCES[key] = new_entity
            new_entity.identifier = key
        self.write('OK')

    def get(self, key):
        # find a parser for the data format the client provided...
        parser = self.get_pyocci_parser('Accept')

        if key in RESOURCES.keys():
            entity = RESOURCES[key]

            # trigger backend to get the freshest results
            backend = registry.get_backend(entity.kind)
            backend.retrieve(entity)

            # get a rendering of this entity...
            heads, data = parser.from_entity(entity)

            self._send_response(heads, data)
        elif key == '/':
            # render a list of resources...
            heads, data = parser.from_entities(RESOURCES.values())
            self._send_response(heads, data)
        else:
            raise HTTPError(404)

    def delete(self, key):
        if key in RESOURCES.keys():
            entity = RESOURCES[key]

            # trigger backend to delete the resource
            backend = registry.get_backend(entity.kind)
            backend.delete(entity)

            RESOURCES.pop(key)
            self.write('OK')
        else:
            raise HTTPError(404)

    def _create_key(self, entity):
        '''
        Create a key with the hierarchy of the entity encapsulated.
        
        @param entity: The entity to create the key for.
        @type entity: Entity
        '''
        # FIXME: handle name-spaces here...
        # pylint: disable=R0201
        key = entity.kind.location + str(uuid.uuid4())
        entity.identifier = key
        return key

class ListHandler(BaseHandler):
    '''
    This class handles listing of resources in REST resource hierarchy and
    listing, adding and removing resource intstance from mixins.
    '''

    # disabling 'Too many public methods' pylint check (tornado's fault)
    # disabling 'Arguments number differs from ...' pylint check 
    #                                               (methods exists twice...)
    # disabling 'Method could be a function' pylint check (I want it here)
    # pylint: disable=R0904,W0221,R0201 

    def get_locations(self):
        '''
        Returns a dict with all categories which have locations.
        '''
        # FIXME: move this up to self.locations...
        locations = {}
        for cat in registry.BACKENDS.keys():
            if hasattr(cat, 'location') and cat.location is not '':
                locations[cat.location] = cat
        return locations

    def get(self, key):
        key = '/' + key + '/'
        headers, body = self.extract_http_data()

        return_parser = self.get_pyocci_parser('Accept')
        categories = None
        try:
            data_parser = self.get_pyocci_parser('Content-Type')
            categories = data_parser.to_categories(headers, body)
        except (KeyError, ParsingException):
            pass

        locations = self.get_locations()
        resources = []

        for name in RESOURCES.keys():
            res = RESOURCES[name]
            if key in locations:
                if res.kind == locations[key]:
                    resources.append(res)
                elif locations[key] in res.mixins:
                    resources.append(res)
            elif name.find(key) > -1 and key.endswith('/'):
                if categories is None:
                    resources.append(res)
                elif len(categories) > 0:
                    for category in categories:
                        if category == res.kind:
                            resources.append(res)
                        elif category in res.kind.related:
                            resources.append(res)
                        elif category in res.mixins:
                            resources.append(res)
        if len(resources) > 0:
            heads, data = return_parser.from_entities(resources)
            return self._send_response(heads, data)
        else:
            raise HTTPError(404)

    def put(self, key):
        key = '/' + key + '/'
        headers, body = self.extract_http_data()
        # find a parser for the data format the client provided...
        parser = self.get_pyocci_parser('Content-Type')

        locations = self.get_locations()

        if key in locations:
            try:
                category = locations[key]
                entities = parser.get_entities(headers, body)
                for item in entities:
                    if RESOURCES.has_key(item):
                        res = RESOURCES[item]
                        if category not in res.mixins:
                            res.mixins.append(category)
            except ParsingException as pse:
                raise HTTPError(400, log_message = str(pse))
        else:
            raise HTTPError(400, 'Put is only allowed on a location path.')

    def delete(self, key):
        key = '/' + key + '/'
        headers, body = self.extract_http_data()
        # find a parser for the data format the client provided...
        parser = self.get_pyocci_parser('Content-Type')

        locations = self.get_locations()

        if key in locations:
            try:
                category = locations[key]
                entities = parser.get_entities(headers, body)
                for item in entities:
                    if RESOURCES.has_key(item):
                        RESOURCES[item].mixins.remove(category)
            except ParsingException as pse:
                raise HTTPError(400, log_message = str(pse))
        else:
            raise HTTPError(400, 'Put is only allowed on a location path.')

class QueryHandler(BaseHandler):
    '''
    This class represents the OCCI query interface.
    '''

    # disabling 'Too many public methods' pylint check (tornado's fault)
    # pylint: disable=R0904

    def get(self):
        parser = self.get_pyocci_parser('Accept')
        heads, data = parser.from_categories(registry.BACKENDS.keys())
        self._send_response(heads, data)

    def put(self):
        headers, body = self.extract_http_data()
        parser = self.get_pyocci_parser('Content-Type')

        try:
            categories = parser.to_categories(headers, body)
            for tmp in categories:
                if isinstance(tmp, Mixin):
                    registry.register_backend([tmp], MixinBackend())
                else:
                    raise ParsingException('Not a valid mixin.')
        except (ParsingException, AttributeError) as pse:
            raise HTTPError(400, log_message = str(pse))

    def delete(self):
        headers, body = self.extract_http_data()
        parser = self.get_pyocci_parser('Content-Type')

        try:
            categories = parser.to_categories(headers, body)
            for tmp in categories:
                if isinstance(tmp, Mixin):
                    registry.unregister_backend([tmp])
                else:
                    raise ParsingException('This mixin is not registered.')
        except ParsingException as pse:
            raise HTTPError(400, log_message = str(pse))

class MixinBackend(Backend):
    '''
    This backend is registered for each user defined Mixin. It does nothing.
    '''

    def create(self, entity):
        pass

    def retrieve(self, entity):
        pass

    def update(self, old_entity, new_entity):
        pass

    def delete(self, entity):
        pass

    def action(self, entity, action):
        pass

class LinkBackend(Backend):
    '''
    This class will be handling the basic Links. If the user defines a kind
    which relates to OCCI-Link it must derive from this class.
    '''

    def create(self, link):
        if link.source is '':
            raise AttributeError('A link needs to have a source.')
        if link.target is '':
            raise AttributeError('A link needs to have a target.')

        try:
            src = RESOURCES[link.source]

            src.links.append(link)
        except KeyError:
            raise AttributeError('Source and target need to be valid Resources')

    def retrieve(self, link):
        pass

    def update(self, old, new):
        if new.source is not '':
            try:
                old_src = RESOURCES[old.source]
                new_src = RESOURCES[new.source]

                old_src.links.remove(old)

                old.source = new.source
                new_src.links.append(old)

            except KeyError:
                raise AttributeError('Source and target need to be valid'
                                     + ' Resources')
        if new.target is not '':
            old.target = new.target
        if len(new.attributes.keys()) > 0:
            old.attributes = new.attributes

    def delete(self, link):
        try:
            src = RESOURCES[link.source]

            src.links.remove(link)
        except KeyError:
            raise AttributeError('Source and target need to be valid Resources')

    def action(self, entity, action):
        pass