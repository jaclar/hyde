# -*- coding: utf-8 -*-
"""
Contains classes to handle images related things

# Requires PIL
"""

from hyde.plugin import Plugin

import re
import Image
from HTMLParser import HTMLParser

class CssHTMLParser(HTMLParser):
    def __init__(self,selector,callback):
        HTMLParser.__init__(self)
        self._callback = callback
        # parsing the selector
        self._selector = self._parse_selector(selector)
        print "len selector: %d"%len(self._selector)
        self._selector_pos = 0
        self._selector_tag_tmp = False

    def _parse_selector(self,selector):
        """
        The parsed selector will be an array with dicts as elements
        which have the form:
        {'tag':"nameOfTag", 'id':"nameOfID", 'class':["nameOfClass1","nameOfClass2",...]}
        """
        parsed = []
        for el in selector.split():
            element = {'tag':'', 'id':'', 'class':[]}
            classes = el.split('.')
            first = classes.pop(0)
            element['class'] = classes
            if first == '':
                pass
            elif first[0] == '#':
                element['id'] = first[1:]
            else:
                element['tag'] = first
            parsed.append(element)
        return parsed

    def handle_starttag(self,tag,attrs):
        print "____________________________"
        print "tag: %s"%tag
        print "selector pos: %d"%self._selector_pos
        if self._selector_pos >= len(self._selector):
            self._selector_pos += 1
            return
        sel = self._selector[self._selector_pos]
        classes = []
        ID = ''
        for attr in attrs:
            if attr[0] == 'class':
                classes = attr[1].split()
            elif attr[0] == 'id':
                ID = attr[1]
        if (sel['tag'] == tag or sel['tag'] == '') and \
           (sel['id'] == ID or sel['id'] == '') and \
           set(sel['class']).issubset(classes):
            self._selector_pos += 1
            if(sel['tag'] == ''):
                self._selector[self._selector_pos]['tag'] = tag
                self._selector_tag_tmp = True
        if self._selector_pos == len(self._selector):
            self._callback(self.getpos(), tag, attrs, self.get_starttag_text())
        return

    def handle_endtag(self,tag):
        if self._selector_pos == len(self._selector):
            if self._selector_tag_tmp:
                self._selector_tag_tmp = False
                self._selector[self._selector_pos]['tag'] = ''
            self._selector_pos -=1
        if self._selector_pos >= len(self._selector):
            self._selector_pos -= 1
            return



class ImageSizerPlugin(Plugin):
    """
    Each HTML page is modified to add width and height for images if
    they are not already specified.
    """

    def __init__(self, site):
        super(ImageSizerPlugin, self).__init__(site)
        self.cache = {}

    def _handle_img(self, resource, src, width, height):
        """Determine what should be added to an img tag"""
        if height is not None and width is not None:
            return ""           # Nothing
        if src is None:
            self.logger.warn("[%s] has an img tag without src attribute" % resource)
            return ""           # Nothing
        if src not in self.cache:
            if src.startswith(self.site.config.media_url):
                path = src[len(self.site.config.media_url):].lstrip("/")
                path = self.site.config.media_root_path.child(path)
                image = self.site.content.resource_from_relative_deploy_path(path)
            elif re.match(r'([a-z]+://|//).*', src):
                # Not a local link
                return ""       # Nothing
            elif src.startswith("/"):
                # Absolute resource
                path = src.lstrip("/")
                image = self.site.content.resource_from_relative_deploy_path(path)
            else:
                # Relative resource
                path = resource.node.source_folder.child(src)
                image = self.site.content.resource_from_path(path)
            if image is None:
                self.logger.warn(
                    "[%s] has an unknown image" % resource)
                return ""       # Nothing
            if image.source_file.kind not in ['png', 'jpg', 'jpeg', 'gif']:
                self.logger.warn(
                        "[%s] has an img tag not linking to an image" % resource)
                return ""       # Nothing
            # Now, get the size of the image
            try:
                self.cache[src] = Image.open(image.path).size
            except IOError:
                self.logger.warn(
                    "Unable to process image [%s]" % image)
                self.cache[src] = (None, None)
                return ""       # Nothing
            self.logger.debug("Image [%s] is %s" % (src,
                                                    self.cache[src]))
        new_width, new_height = self.cache[src]
        if new_width is None or new_height is None:
            return ""           # Nothing
        if width is not None:
            return 'height="%d" ' % (int(width)*new_height/new_width)
        elif height is not None:
            return 'width="%d" ' % (int(height)*new_width/new_height)
        return 'height="%d" width="%d" ' % (new_height, new_width)

    def text_resource_complete(self, resource, text):
        """
        When the resource is generated, search for img tag and specify
        their sizes.

        Some img tags may be missed, this is not a perfect parser.
        """
        try:
            mode = self.site.config.mode
        except AttributeError:
            mode = "production"

        if not resource.source_file.kind == 'html':
            return

        if mode.startswith('dev'):
            self.logger.debug("Skipping sizer in development mode.")
            return

        pos = 0                 # Position in text
        img = None              # Position of current img tag
        state = "find-img"
        while pos < len(text):
            if state == "find-img":
                img = text.find("<img", pos)
                if img == -1:
                    break           # No more img tag
                pos = img + len("<img")
                if not text[pos].isspace():
                    continue        # Not an img tag
                pos = pos + 1
                tags = {"src": "",
                        "width": "",
                        "height": ""}
                state = "find-attr"
                continue
            if state == "find-attr":
                if text[pos] == ">":
                    # We get our img tag
                    insert = self._handle_img(resource,
                                              tags["src"] or None,
                                              tags["width"] or None,
                                              tags["height"] or None)
                    img = img + len("<img ")
                    text = "".join([text[:img], insert, text[img:]])
                    state = "find-img"
                    pos = pos + 1
                    continue
                attr = None
                for tag in tags:
                    if text[pos:(pos+len(tag)+1)] == ("%s=" % tag):
                        attr = tag
                        pos = pos + len(tag) + 1
                        break
                if not attr:
                    pos = pos + 1
                    continue
                if text[pos] in ["'", '"']:
                    pos = pos + 1
                state = "get-value"
                continue
            if state == "get-value":
                if text[pos] == ">":
                    state = "find-attr"
                    continue
                if text[pos] in ["'", '"'] or text[pos].isspace():
                    # We got our value
                    pos = pos + 1
                    state = "find-attr"
                    continue
                tags[attr] = tags[attr] + text[pos]
                pos = pos + 1
                continue

        return text


class ImageFigurePlugin(Plugin):
    """
    Each HTML page is modified to add a figure environment around every
    img tag. The alt text will be transformed to a capiton.
    """

    def __init__(self, site):
        super(ImageFigurePlugin, self).__init__(site)
        self.cache = {}

    def text_resource_complete(self, resource, text):
        """
        When the resource is generated, search for img tag and add
        it to a figure environment.

        Some img tags may be missed, this is not a perfect parser.
        (parser taken from ImageSizerPlugin)
        """
        if not resource.source_file.kind == 'html':
            return

        pos = 0                 # Position in text
        img = None              # Position of current img tag
        state = "find-img"
        while pos < len(text):
            if state == "find-img":
                img = text.find("<img", pos)
                if img == -1:
                    break           # No more img tag
                pos = img + len("<img")
                if not text[pos].isspace():
                    continue        # Not an img tag
                pos = pos + 1
                tags = {"alt": "",
                        "title": "",
                        "class": ""}
                state = "find-attr"
                continue
            if state == "find-attr":
                if text[pos] == ">":
                    # We get our img tag
                    # looking for the "no-figure" class
                    if tags['class'].find("no-figure") != -1:
                        state = "find-img"
                        continue
                    if tags['alt'] != "":
                        cap = tags['alt']
                    elif tags['title'] != "":
                        cap = tags['title']
                    else:
                        self.logger.warn(
                            "[%s] has an image without alt text" % resource)
                        state = "find-img"
                        continue

                    startfigure = "\n<figure>\n  "
                    caption = "\n  <figcaption>%s</figcaption>\n"%cap
                    endfigure = "</figure>\n"
                    pos = pos + 1
                    text = "".join([text[:img],
                                    startfigure,
                                    text[img:pos],
                                    caption,
                                    endfigure,
                                    text[pos:]])
                    state = "find-img"
                    continue
                attr = None
                for tag in tags:
                    if text[pos:(pos+len(tag)+1)] == ("%s=" % tag):
                        attr = tag
                        pos = pos + len(tag) + 1
                        break
                if not attr:
                    pos = pos + 1
                    continue
                if text[pos] in ["'", '"']:
                    pos = pos + 1
                state = "get-value"
                continue
            if state == "get-value":
                if text[pos] == ">":
                    state = "find-attr"
                    continue
                if text[pos] in ["'", '"']:
                    # We got our value
                    pos = pos + 1
                    state = "find-attr"
                    continue
                tags[attr] = tags[attr] + text[pos]
                pos = pos + 1
                continue

        return text
