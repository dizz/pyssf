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
This module contains all backends.

Created on Jul 9, 2010

@author: tmetsch
'''
from resource_model import JobResource, Link

class Handler(object):

    def create(self, resource):
        # add links to resource
        raise NotImplementedError

    def update(self, resource):
        # update attributes
        raise NotImplementedError

    def get(self, resource):
        # return updated attributes & links
        raise NotImplementedError

    def delete(self, resource):
        # update attributes & cleanup
        pass

    def action(self, resource):
        # trigger action & update state/attributes
        pass

class SSFHandler(Handler):

    def create(self, resource):
        if isinstance(resource, JobResource):
            link = Link()
            link.link_class = 'action'
            link.rel = 'http://purl.org/occi/job/action#kill'
            link.target = '/' + resource.id + ';kill'
            link.title = 'Kill Job'
            resource.links.append(link)
        else:
            pass

        # add a link

