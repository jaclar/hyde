"""
Contains classes and utilities for serving a site
generated from hyde.
"""
import os
import urlparse
import urllib
from SimpleHTTPServer import SimpleHTTPRequestHandler
from BaseHTTPServer import HTTPServer
from hyde.fs import File, Folder
from hyde.site import Site
from hyde.generator import Generator

import logging

logger = logging.getLogger('hyde.server')

import sys
logger.addHandler(logging.StreamHandler(sys.stdout))

class HydeRequestHandler(SimpleHTTPRequestHandler):
    """
    Serves files by regenerating the resource (or)
    everything when a request is issued.
    """

    def do_GET(self):
        """
        Idenitfy the requested path. If the query string
        contains `refresh`, regenerat the entire site.
        Otherwise, regenerate only the requested resource
        and serve.
        """
        logger.info("Processing request:[%s]" % self.path)
        result = urlparse.urlparse(self.path)
        query = urlparse.parse_qs(result.query)
        if 'refresh' in query:
            self.server.regenerate()
            del query['refresh']
            parts = tuple(result)
            parts[4] = urllib.urlencode(query)
            new_url = urlparse.urlunparse(parts)
            logger.info('Redirecting...[%s]' % new_url)
            self.redirect(new_url)
        else:
            try:
                SimpleHTTPRequestHandler.do_GET(self)
            except Exception, exception:
                logger.error(exception.message)
                site = self.server.site
                res = site.content.resource_from_relative_path(
                        site.config.not_found)
                self.redirect("/" + res.relative_deploy_path)

    def translate_path(self, path):
        """
        Finds the absolute path of the requested file by
        referring to the `site` variable in the server.
        """
        site = self.server.site
        result = urlparse.urlparse(self.path)
        logger.info("Trying to load file based on request:[%s]" % result.path)
        path = result.path.lstrip('/')
        res = site.content.resource_from_relative_deploy_path(path)
        if not res:
            # Cannot find the source file using the given path.
            # Check if the target file exists in the deploy folder.
            deployed = File(site.config.deploy_root_path.child(path))
            if deployed.exists:
              # this file is probably being generated by a plugin.
              # lets not try too hard, just regenerate
              self.server.regenerate()
              return deployed.path
            else:
                logger.info("Cannot load file:[%s]" % path)
                raise Exception("Cannot load file: [%s]" % path)

        else:
            self.server.generate_resource(res)
        new_path = site.config.deploy_root_path.child(
                    res.relative_deploy_path)
        return new_path

    def redirect(self, path, temporary=True):
        """
        Sends a redirect header with the new location.
        """
        self.send_response(302 if temporary else 301)
        self.send_header('Location', path)
        self.end_headers()


class HydeWebServer(HTTPServer):
    """
    The hyde web server that regenerates the resource, node or site when
    a request is issued.
    """

    def __init__(self, site, address, port):
        self.site = site
        self.site.load()
        self.exception_count = 0
        self.generator = Generator(self.site)

        HTTPServer.__init__(self, (address, port),
                                            HydeRequestHandler)

    def __reinit__(self):
        self.generator = Generator(self.site)
        self.regenerate()

    def regenerate(self):
        """
        Regenerates the entire site.
        """
        try:
            logger.info('Regenerating the entire site')
            self.generator.generate_all()
        except Exception, exception:
            self.exception_count += 1
            logger.error('Error occured when regenerating the site [%s]'
                            % exception.message)
            if self.exception_count <= 1:
                self.__reinit__()


    def generate_resource(self, resource):
        """
        Regenerates the entire site.
        """
        try:
            logger.info('Generating resource [%s]' % resource)
            self.generator.generate_resource(resource)
        except Exception, exception:
            logger.error('Error [%s] occured when generating the resource [%s]'
                            % (repr(exception), resource))
            raise
