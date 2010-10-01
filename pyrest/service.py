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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
# 
'''
This module contains the RESTful service itself.

Created on Jul 2, 2010

@author: tmetsch
'''

from pyrest import backends
from pyrest.myexceptions import MissingActionException, \
    MissingAttributesException, StateException, MissingCategoriesException, \
    SecurityException
from pyrest.rendering_parsers import HTTPHeaderParser, HTTPTextParser, \
    HTTPListParser, HTTPData, HTTPHTMLParser
import re
import uuid
import web

DEFAULT_RENDERING_PARSER = HTTPHeaderParser()
RENDERING_PARSERS = {'text/plain': HTTPTextParser(),
                     '*/*': HTTPHeaderParser(),
                     'text/uri-list': HTTPListParser(),
                     'text/html': HTTPHTMLParser(),
                     'text/html;q=0.9':HTTPHTMLParser()}
AUTHENTICATION_ENABLED = False

# some helper routines.

def find_parser():
    """
    In case of requests: Tries to resolve the right parser based on the Accept
    Header the client sends - If non can be found or no header is defined the
    default header is returned.
    
    In case of posts: Tries to resolve based upon the specified content-type
    header. If non is specified it will return the default.
    """
    # post & put
    if 'REQUEST_METHOD' in web.ctx.env:
        if web.ctx.env['REQUEST_METHOD'] == 'PUT' or web.ctx.env['REQUEST_METHOD'] == 'POST':
            # put or post so -> check content type
            if 'HTTP_CONTENT_TYPE' in web.ctx.env:
                # select parser based on content_type
                try:
                    return RENDERING_PARSERS[web.ctx.env['HTTP_CONTENT_TYPE']]
                except KeyError:
                    return DEFAULT_RENDERING_PARSER
    if 'HTTP_ACCEPT' in web.ctx.env:
        try:
            for key in RENDERING_PARSERS.keys():
                if key in web.ctx.env['HTTP_ACCEPT'].split(','):
                    return RENDERING_PARSERS[key]
        except KeyError:
            return DEFAULT_RENDERING_PARSER
    #return default
    return DEFAULT_RENDERING_PARSER

def authenticate(target):
    """
    Authenticate the user.
    """
    def wrapper(*args, **kwargs):
        if AUTHENTICATION_ENABLED:
            if SECURITY_HANDLER is None:
                return web.Unauthorized("Could not determine an security"
                                        + "handler.")
            try:
                if 'HTTP_AUTHORIZATION' in web.ctx.env:
                    # when using basic oAuth.
                    import base64
                    tmp = web.ctx.env['HTTP_AUTHORIZATION'].lstrip('Basic ')
                    credentials = base64.b64decode(tmp).split(':')
                    username = credentials[0]
                    password = credentials[1]
                    SECURITY_HANDLER.authenticate(username, password)
                elif 'HTTP_SSL_CLIENT_CERT_DN' in web.ctx.env:
                    # when using Apache mod_wsgi
                    username = web.ctx.env['HTTP_SSL_CLIENT_CERT_DN'].strip()
                else:
                    raise SecurityException("Could not find user information.")
            except BaseException:
                return web.Unauthorized()
            else:
                kwargs.update({'username': username})
                return target(*args, **kwargs)
        else:
            return target(*args)

    return wrapper

def validate_key(name):
    """
    Decorator to validate the given keys!
    """
    valid_key = re.compile('[a-zA-Z0-9-]*')
    def new(*args, **kwargs):
        """
        Checks the arguments.
        """
        if valid_key.match(args[1]) is None:
            web.BadRequest(), 'Invalid key provided!'
        return name(*args, **kwargs)
    return new

# The following stuff is here for Storage of the Resources.

class NonPersistentResourceDictionary(dict):
    """
    Overrides a dictionary - Since the resource model and rendering parsers are
    generic this is the most interesting part.
    
    Whenever a item is added or removed, a parser will be called to update the
    resource description.
    """

    def __init__(self):
        dict.__init__(self)

    def __getitem__(self, key):
        try:
            item = dict.__getitem__(self, key)
        except KeyError:
            raise
        return find_parser().from_resource(item)

    def __setitem__(self, key, value):
        try:
            item = find_parser().to_resource(key, value)
        except MissingCategoriesException:
            raise

        return dict.__setitem__(self, key, item)

    def __delitem__(self, key):
        return dict.__delitem__(self, key)

    def get_resource(self, key):
        """
        Returns the resource without parsing it back to HTTP data.
        """
        try:
            return dict.__getitem__(self, key)
        except KeyError:
            raise

#class PersistentResourceDictionary(dict):
#    """
#    Persistently stores the dictionary to a database to be failsafe.
#    
#    http://docs.python.org/library/shelve.html
#    """
#    pass

# The following part is here for basic HTTP handling.

class SecurityHandler(object):
    """
    A security handler.
    """

    def authenticate(self, username, password):
        """
        Authenticate a user with it's password.
        """
        raise SecurityException("Could not authenticate user.")

    def authorize(self, username, resource):
        """
        Very basic authorization which only assures that users do not
        interfere with each other.
        """
        if not username == resource.user:
            raise SecurityException("Not authorized.")

SECURITY_HANDLER = SecurityHandler()

class HTTPHandler(object):
    """
    Handles the very basic HTTP operations. The logic when a resource is
    created, updated or delete is handle in here. It makes later replacements
    of the protocol easier. Do not mixup protocol and rendering. XML can be
    rendered over HTTP for example.
    """

    @authenticate
    @validate_key
    def POST(self, name, username = "default"):
        """
        Handles the POST request - triggers creation of a resource. Will
        return a location of the newly created resource.
        
        name -- the id of the resource.
        *data -- if available (this it the body of the HTTP message).
        """
        # handle actions
        index = web.ctx.env['PATH_INFO'].find(';action=')
        if index is not - 1:
            key = web.ctx.env['PATH_INFO'][1:index]
            try:
                request = HTTPData(web.ctx.env, web.data())
                self.trigger_action(key, request, username)
                web.OK()
                return 'OK'
            except (StateException, MissingCategoriesException,
                    MissingActionException) as ex:
                return web.BadRequest(), str(ex)
            except KeyError:
                return web.NotFound()
            except SecurityException as se:
                return web.Unauthorized(), str(se)

        # create a new sub resource
        request = HTTPData(web.ctx.env, web.data())
        name = str(name)
        if self.resource_exists(name) is True:
            try:
                if name.endswith('/') or len(name) == 0:
                    name += str(uuid.uuid4())
                else:
                    name += '/' + str(uuid.uuid4())
                self.create_resource(str(name), request, username)
                web.header("Location", "/" + str(name))
                return 'OK'
            except (MissingCategoriesException,
                    MissingAttributesException, NotImplementedError) as ex:
                return web.BadRequest(), str(ex)
        else:
            return web.NotFound("Couldn't create sub resource of non-existing"
                                + "resource.")

    @authenticate
    @validate_key
    def GET(self, name, username = 'default'):
        """
        Handles the GET request - triggers the service to return information.
        
        name -- the id of the resource.
        *data -- if available (this it the body of the HTTP message).
        """
        name = str(name)
        tmp = None
        try:
            tmp = self.return_resource(name, username)
        except KeyError:
            tmp = self.list_resources(name, username)
        except MissingAttributesException as mae:
            return web.BadRequest(), str(mae)
        except SecurityException as se:
            return web.Unauthorized(), str(se)

        if tmp is not None:
            for item in tmp.header.keys():
                web.header(item, tmp.header[item])
            if tmp.body is None:
                return 'All data is in the headers...'
            else:
                return tmp.body
        else:
            return web.NotFound()

    @authenticate
    @validate_key
    def PUT(self, name = None, username = "default"):
        """
        Handles the PUT request - triggers either the creation or updates a 
        resource.
        
        name -- if available (the id of the resource).
        *data -- if available (this it the body of the HTTP message).
        """
        # if exists - update; else create
        request = HTTPData(web.ctx.env, web.data())
        name = str(name)
        if self.resource_exists(name) is True:
            try:
                self.update_resource(name, request, username)
            except MissingCategoriesException as mce:
                return web.BadRequest(), str(mce)
            except SecurityException as se:
                return web.Unauthorized(), str(se)
            else:
                web.OK()
                return 'OK'
        else:
            try:
                self.create_resource(name, request, username)
            except (MissingCategoriesException,
                    MissingAttributesException) as ex:
                return web.BadRequest(), str(ex)
            else:
                web.OK()
                return 'OK'

    @authenticate
    @validate_key
    def DELETE(self, name, username = "default"):
        """
        Handles the DELETE request.
        
        name -- the id of the resource).
        """
        # delete a resource representation
        if self.resource_exists(name):
            try:
                self.delete_resource(str(name), username)
            except KeyError:
                return web.NotFound()
            except MissingAttributesException as mae:
                return web.InternalError(str(mae))
            except SecurityException as se:
                return web.Unauthorized(), str(se)
            else:
                web.OK()
                return 'OK'
        else:
            return web.NotFound()

# The final part actually does something.

class ResourceHandler(HTTPHandler):
    """
    Manages the resources and stores them. Also triggers backend operations. It
    is protocol and rendering free.
    """

    resources = NonPersistentResourceDictionary()

    def create_resource(self, key, data, username):
        """
        Creates a resource.
        
        key -- the unique id.
        data -- the data.
        """
        try:
            self.resources[key] = data
            self.resources.get_resource(key).user = username
            resource = self.resources.get_resource(key)
            # trigger backend to do some magic
            backend = backends.find_right_backend(resource.categories)
            backend.create(resource)
        except (MissingCategoriesException, MissingAttributesException):
            raise

    def return_resource(self, key, username):
        """
        Returns a resource.
        
        key -- the unique id.
        data -- the data.
        """
        try:
            # trigger backend to get resource
            res = self.resources.get_resource(key)
            SECURITY_HANDLER.authorize(username, res)
            backend = backends.find_right_backend(res.categories)
            backend.retrieve(res)
            res = self.resources[key]
            return res
        except (KeyError, MissingAttributesException, SecurityException):
            raise

    def update_resource(self, key, data, username):
        """
        Updates a resource.
        
        key -- the unique id.
        data -- the data.
        """
        # trigger backend and tell him there was an update
        # only backend update the real resource - incl checks what can be 
        #   changed and what not :-)
        try:
            #self.resources[key] = data
            res = self.resources.get_resource(key)
            SECURITY_HANDLER.authorize(username, res)
            backend = backends.find_right_backend(res.categories)
            backend.update(res, find_parser().to_resource('tmp', data))
        except (KeyError, MissingAttributesException, SecurityException):
            raise

    def delete_resource(self, key, username):
        """
        Deletes a resource.
        
        key -- the unique id.
        """
        try:
            # trigger backend to delete
            res = self.resources.get_resource(key)
            SECURITY_HANDLER.authorize(username, res)
            backend = backends.find_right_backend(res.categories)
            backend.delete(res)
            del(self.resources[key])
        except (KeyError, MissingAttributesException, SecurityException):
            raise

    def trigger_action(self, key, data, username):
        """
        Trigger an action in the backend system. Backend should update state
        and links if needed.
        
        key -- the id for the resource.
        data -- HTTP data for the action request.
        """
        try:
            res = self.resources.get_resource(key)
            SECURITY_HANDLER.authorize(username, res)
            action = find_parser().to_action(data)
            backend = backends.find_right_backend(res.categories)
            backend.action(res, action)
        except (KeyError, MissingCategoriesException, MissingActionException,
                StateException, SecurityException):
            raise

    def list_resources(self, key, username):
        resources = []
        for name in self.resources.keys():
            res = self.resources.get_resource(name)
            if res.user == username and name == key:
                resources.append(res)
            elif res.user == username and key == '':
                resources.append(res)
            elif res.user == username and name.find(key) > -1 and key.endswith('/'):
                resources.append(res)
            # TODO: check for category as well...
        if len(resources) > 0:
            # we found some resources
            data = find_parser().from_resources(resources)
            return data
        elif key == "":
            # client requested root
            return find_parser().from_resources([])
        else:
            # no result...
            return None

    def resource_exists(self, key):
        """
        Tests if an resource exists.
        
        key -- the id to look for...
        """
        if self.resources.has_key(key) or key is '':
            return True
        else:
            return False

class QueryHandler(object):
    """
    Represents the Query interface.
    """

    def GET(self, name):
        if len(name) == 0:
            parser = find_parser()
            http_data = parser.from_categories(backends.REGISTERED_BACKENDS.keys())
            for item in http_data.header.keys():
                web.header(item, http_data.header[item])
            return http_data.body
        else:
            return web.BadRequest()
