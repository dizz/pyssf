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
Created on Jul 20, 2010

@author: tmetsch
'''
from backends import Handler
from resource_model import Link

class DummyBackend(Handler):

    def create(self, resource):
        link = Link()
        link.link_class = 'action'
        link.rel = 'http://purl.org/occi/drmaa/action#release'
        link.target = '/' + resource.id + ';release'
        link.title = 'Kill Job'
        resource.links.append(link)

    def update(self, resource):
        pass

    def retrieve(self, resource):
        pass

    def delete(self, resource):
        pass

    def action(self, resource, action):
        if action == 'release':
            resource.attributes['occi.drmaa.job_state'] = 'EXIT'
        else:
            raise AttributeError('Non existing action called!')

