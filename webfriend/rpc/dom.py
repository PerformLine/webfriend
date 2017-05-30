from __future__ import absolute_import
from . import Base
import logging
import math
import time
from .. import exceptions


class NoSuchElement(Exception):
    pass


class DOMElement(object):
    def __init__(self, rpc, definition):
        self.dom = rpc
        self.populate(definition)

    def populate(self, definition):
        if not isinstance(definition, dict):
            raise AttributeError("DOM Element definition must be a dict")

        if 'nodeId' not in definition or definition['nodeId'] is None:
            raise AttributeError("DOM Element definition must contain 'nodeId'")

        if 'nodeName' not in definition:
            self._partial = True
        else:
            self._partial = False

        self.definition  = definition
        self.id          = definition['nodeId']
        self.parent_id   = definition.get('parentId')
        self.type        = definition.get('nodeType')
        self.local_name  = definition.get('localName')
        self.attributes  = {}
        self._box_model  = None
        self._name       = definition.get('nodeName')
        self._value      = definition.get('nodeValue')
        self.child_nodes = []
        self._text       = u''
        self.child_ids   = set()
        self._bounding_rect = None

        # populate children
        if len(definition.get('children', [])):
            for child in definition['children']:
                child_type = child.get('nodeType')

                if child_type == 1:
                    self.child_ids.add(child['nodeId'])

                elif child_type == 3:
                    self._text = child.get('nodeValue', u'')

                else:
                    self.child_nodes.append(DOMElement(self.dom, child))

        # populate attributes
        if len(definition.get('attributes', [])):
            attrgen = (a for a in definition['attributes'])

            for name, value in [(n, attrgen.next()) for n in attrgen]:
                self.attributes[name] = value

    def evaluate(self, script, return_by_value=False, own_properties=False, accessors_only=True):
        remote_object = self.dom.call('resolveNode', nodeId=self.id).result.get('object', {})
        object_id = remote_object['objectId']

        print('GOT: {}'.format(object_id))

        # retrieve details via script injection
        try:
            # call the function to retrieve runtime position info
            result = self.dom.tab.runtime.call_function_on(
                object_id,
                "function(){{ {} }}".format(script),
                return_by_value=return_by_value,
            ).result.get('result')

            # if we asked to return the value, then do so now
            if return_by_value:
                return result

            result_id = result.get('objectId')

            if result_id:
                # retrieve the object that resulted from that call
                properties = self.dom.tab.runtime.get_properties(
                    result_id,
                    own_properties=own_properties,
                    accessors_only=accessors_only
                ).result.get('result', [])

                # release that object
                self.dom.tab.runtime.release_object(result_id)

            # return the data
            return dict([
                (p['name'], p.get('value', {}).get('value')) for p in properties if not p['name'].startswith('_')
            ])

        finally:
            if not return_by_value:
                self.dom.tab.runtime.release_object(object_id)

    def click(self, ensure_target=True, scroll_to=True):
        if self.attributes.get('target') == '_blank':
            del self['target']

        # if specified, scroll down to the element if it's below the fold
        if scroll_to:
            if self.top > self.dom.root.height:
                self.scroll_to()

        return self.evaluate("return this.click()", return_by_value=True)

    def scroll_to(self, x=None, y=None):
        if x is None:
            x = 0

        if y is None:
            y = self.top

        return self.evaluate(
            "window.scrollTo({}, {})".format(x, y),
            return_by_value=True
        )

    @property
    def is_partial(self):
        return self._partial

    @property
    def name(self):
        return self._name

    # @name.setter
    # def name(self, v):
    #     response = self.dom.call('setNodeName', nodeId=self.id, name='{}'.format(v))
    #     return response.get('params', {})['nodeId']

    @property
    def text(self):
        return self._text

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        self.dom.call('setNodeValue', nodeId=self.id, value='{}'.format(v))

    @property
    def outer_html(self):
        return self.dom.call('getOuterHTML', nodeId=self.id).get('outerHTML')

    @outer_html.setter
    def outer_html(self, value):
        self.call('setOuterHTML', nodeId=self.id, outerHTML=value)

    def refresh_attributes(self):
        pairs = self.dom.call('getAttributes', nodeId=self.id).get('attributes', [])
        attrgen = (a for a in pairs)
        attrs = {}

        for name, value in [(n, attrgen.next()) for n in attrgen]:
            attrs[name] = value

        self.attributes = attrs

        return self.attributes

    @property
    def children(self):
        out = []

        for i in self.child_ids:
            el = self.dom.element(i)

            if el:
                out.append(el)

        return out

    def recheck_box(self):
        self._box_model = None
        return self.box

    def recheck_bounds(self):
        self._bounding_rect = None
        return self.bounds

    @property
    def bounds(self):
        if self._bounding_rect is None:
            self._bounding_rect = self.evaluate("return this.getBoundingClientRect();")

        return self._bounding_rect

    @property
    def box(self):
        if self._box_model is None:
            self._box_model = self.dom.call('getBoxModel', nodeId=self.id).get('model')

        return self._box_model

    @property
    def parent(self):
        return self.dom.element(self.parent_id)

    @property
    def width(self):
        return int(math.ceil(self.bounds.get('width', self.box['width'])))

    @property
    def height(self):
        return int(math.ceil(self.bounds.get('height', self.box['height'])))

    @property
    def top(self):
        return self.bounds.get('top')

    @property
    def right(self):
        return self.bounds.get('right')

    @property
    def bottom(self):
        return self.bounds.get('bottom')

    @property
    def left(self):
        return self.bounds.get('left')

    def query(self, selector):
        return self.dom.query(selector, node_id=self.id)

    def query_all(self, selector):
        return self.dom.query_all(selector, node_id=self.id)

    def xpath(self, expression):
        return self.dom.xpath(expression, node_id=self.id)

    def remove(self):
        self.dom.remove(self.id)

    def focus(self):
        self.dom.focus(self.id)

    def __getitem__(self, key):
        if not len(self.attributes):
            self.refresh_attributes()

        return self.attributes[key]

    def __setitem__(self, key, value):
        self.dom.call('setAttributeValue', nodeId=self.id, name=key, value=str(value))

    def __delitem__(self, key):
        self.dom.call('removeAttribute', nodeId=self.id, name=key)

    def __repr__(self):
        if self.name:
            if self.type == 1:
                element_name = self.name.lower()
                attrs = []

                for k, v in self.attributes.items():
                    attrs.append(u'{}="{}"'.format(k, v))

                if len(attrs):
                    attrs = u' ' + u' '.join(attrs)
                else:
                    attrs = u''

                return u'<{}{}>{}</{}>'.format(
                    element_name,
                    attrs,
                    self.text,
                    element_name
                )
            else:
                return u'{} id={}'.format(self.name, self.id)
        else:
            parts = [u'node={}'.format(self.id)]

            if self.name:
                parts.append(u'name={}'.format(self.name))

            return u'DOMElement<{}>'.format(','.join(parts))

    def __str__(self):
        return self.__repr__()


class DOM(Base):
    domain = u'DOM'
    _root_element = None
    _elements = {}

    def initialize(self):
        self.on(u'setChildNodes', self.on_child_nodes)
        self.on(u'childNodeRemoved', self.on_child_removed)
        self.tab.page.on(u'frameStartedLoading', self.reset)

    def reset(self, *args, **kwargs):
        self._root_element = None
        self._elements = {}

    def has_element(self, id):
        if id in self._elements:
            return True
        return False

    def element(self, id, fallback=None):
        return self._elements.get(id, fallback)

    def element_at(self, x, y, shadow=False):
        node_id = self.call(
            'getNodeForLocation',
            x=x,
            y=y,
            includeUserAgentShadowDOM=shadow
        ).get('nodeId')

        if node_id:
            return self.element(node_id)

        return None

    def print_node(self, node_id=None, level=0, indent=4):
        if node_id is None:
            node_id = self.root.id

        node = self.element(node_id)

        if node is not None:
            logging.debug(u'TREE: {}{}'.format((u' ' * indent * level), node))

            for child in node.children:
                self.print_node(child.id, level=level + 1)

    @property
    def root(self):
        if self._root_element is None:
            self.reset()

            self._root_element = DOMElement(
                self,
                self.call('getDocument', depth=0).get('root')
            )

            self._elements[self._root_element.id] = self._root_element

        return self._root_element

    def remove_node(self, node_id):
        self.call('removeNode', nodeId=node_id)

    def focus(self, node_id):
        self.call('focus', nodeId=node_id)

    def query(self, selector, node_id=None, reply_timeout=None):
        if node_id is None:
            node_id = self.root.id

        matched_node_id = self.call(
            'querySelector',
            reply_timeout=reply_timeout,
            selector=self.prepare_selector(selector),
            nodeId=node_id
        ).get('nodeId')

        if not matched_node_id:
            raise NoSuchElement(
                "No elements matched the query selector '{}' under document {}".format(
                    selector,
                    node_id
                )
            )

        return DOMElement(self, {
            'nodeId': matched_node_id,
        })

    def query_all(self, selector, node_id=None, reply_timeout=None):
        if node_id is None:
            node_id = self.root.id

        selector = selector.replace("'", '"')

        node_ids = self.call(
            'querySelectorAll',
            reply_timeout=reply_timeout,
            selector=self.prepare_selector(selector),
            nodeId=node_id
        ).get('nodeIds', [])

        return [
            DOMElement(self, {
                'nodeId': i,
            }) for i in node_ids
        ]

    def xpath(self, expression, node_id=None):
        if node_id is None:
            node_id = self.root.id

        element = self.element(node_id)

        out = element.evaluate(
            """
            var results = document.evaluate('{}', this, null, XPathResult.ANY_TYPE, null);
            var nodes = [];
            var next = results.iterateNext();

            while (next) {{
                nodes.push({{
                    'nodeName': next.nodeName,
                    'nodeType': next.nodeType,
                    'text':     next.text,
                }});
                next = results.iterateNext();
            }}

            return nodes;
            """.format(expression.replace("'", "\\'")),
            return_by_value=True
        )

        print(out)

        return out

    def select_nodes(self, selector, wait_for_match=False, timeout=10000, interval=250):
        """
        Polls the DOM for an element that matches the given selector.  Either the element will be
        found and returned within the given timeout, or a TimeoutError will be raised.

        ### Arguments

        - **selector** (`str`):

            The CSS-style selector that specifies the DOM element to look for.

        - **timeout** (`int`):

            The number of milliseconds to wait for the element to be returned.

        - **interval** (`int`):

            The polling interval, in milliseconds, used for rechecking for the element.

        ### Returns
        `chromefriend.rpc.dom.DOMElement`

        ### Raises
        `chromefriend.exceptions.TimeoutError`
        """
        started_at = time.time()

        while time.time() <= (started_at + (timeout / 1e3)):
            try:
                elements = self.query_all(selector, reply_timeout=interval)

                # if we're not waiting or we are and we've got elements, return
                if not wait_for_match or len(elements):
                    results = {
                        'selector': selector,
                        'count':    len(elements),
                    }

                    # specifically only include nodes in the result if we actually have any
                    # this lets us test for whether 'nodes' is in the result as a pass/fail
                    # for a condition
                    if len(elements):
                        results['nodes'] = [
                            self.element(e.id, e) for e in elements
                        ]

                    return results
            except (
                exceptions.TimeoutError,
                exceptions.ChromeProtocolError
            ):
                pass

            time.sleep(interval / 1e3)

        raise exceptions.TimeoutError(
            "Timed out waiting for element '{}' to appear".format(selector)
        )

    def on_child_nodes(self, event):
        for node in event.get('nodes', []):
            element = DOMElement(self, node)

            # logging.debug('Adding node {} (type={} name={} parent={})'.format(
            #     element.id,
            #     element.type,
            #     element.name,
            #     element.parent_id
            # ))

            self._elements[node['nodeId']] = element

            if self.has_element(element.parent_id):
                self.element(element.parent_id).child_ids.add(element.id)

    def on_child_removed(self, event):
        node_id = event.get('nodeId')
        parent_id = event.get('parentNodeId')

        if self.has_element(parent_id):
            try:
                self.element(parent_id).child_ids.remove(node_id)
            except KeyError:
                pass

        if self.has_element(node_id):
            del self._elements[node_id]

    @classmethod
    def prepare_selector(cls, selector):
        if selector.startswith('#'):
            selector = '*[id="{}"]'.format(selector[1:])

        selector = selector.replace("'", '"')

        return selector

    @classmethod
    def ensure_unique_element(cls, selector, elements):
        if isinstance(elements, dict):
            nodes = elements.get('nodes', [])
        else:
            nodes = elements

        if not len(nodes):
            raise exceptions.EmptyResult("No elements matched the selector: {}".format(
                selector
            ))

        elif len(nodes) > 1:
            raise exceptions.TooManyResults(
                "Selector {} is ambiguous, matched {} elements".format(
                    selector, len(nodes)
                )
            )

        return True
