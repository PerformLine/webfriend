from __future__ import absolute_import
import logging
import time
import io
from .. import CommandProxy
from ... import exceptions


class PageProxy(CommandProxy):
    def screenshot(
        self,
        destination=None,
        width=0,
        height=0,
        format='png',
        jpeg_quality=None,
        selector='html',
        settle=1000,
        after_events=None,
        settle_timeout=None,
        autoclose=True
    ):
        """
        Capture the current screen contents as an image and write the image to a file or return it
        as a file-like object.

        ### Arguments

        - **destination** (`str`, _file-like object_, optional):

            If given as a string, this will be the filesystem path that the image is written to.
            If given as a file-like object, that object will be written to, seeked back to zero,
            and returned.  If `None`, an `io.BytesIO` buffer will be allocated, written to, and
            returned.

        - **width** (`int`, optional):

            If given, this is the width viewport will be resized to before capturing the image. If
            not specified, the dimensions of the element specified by 'selector' will be queried
            and that element's outerWidth will be used.

        - **height** (`int`, optional):

            If given, this is the height viewport will be resized to before capturing the image. If
            not specified, the dimensions of the element specified by **selector** will be queried
            and that element's _outerHeight_ will be used.

        - **format** (`str`):

            The output format of the image, either `png` or `jpeg`.

        - **jpeg_quality** (`int`, optional):

            If given, and if **format** is `jpeg`, this is the quality of the JPEG image (0-100).

        - **selector** (`str`):

            When detecting the width and/or height of the page area to render, this is the HTML
            element that will be measured.

        - **settle** (`int`, optional):

            The number of milliseconds to wait after performing the viewport resize before
            actually capturing the image.  This gives newly-exposed elements time to load.

        - **after_events** (`str`, `list`, optional):

            If an event name or list of event names is given, then **settle** will be interpreted
            as an amount of time _after_ the last of these named events has been received. If the
            special value `any` is provided, then **settle** will wait for that amount of time
            since any event has been received to elapse, up to 'settle_timeout' seconds.

        - **settle_timeout** (`int`, optional):

            The maximum amount of time to wait for events to stop coming in as described in by
            **after_events**.

        - **autoclose** (`bool`):

            If a file handle is given as the **destination**, should it be automatically closed
            when the screenshot is completed.

        ### Returns
        `dict`, with keys:

        - _element_ (`webfriend.rpc.dom.DOMElement`):
            The element that was used as a measurement reference.

        - _width_ (`int`):
            The final width of the viewport that was captured.

        - _height_ (`int`):
            The final height of the viewport that was captured.

        - _destination_ (`object`, optional):
            The destination file-like object data was written to, if specified.

        - _path_ (`str`, optional):
            The filesystem path of the file data was written to, if specified.
        """
        element = self.tab.dom.query(selector)
        return_flo = True

        if not width:
            width = element.width

        if not height:
            height = element.height

        # resize and force redraw
        self.tab.emulation.set_visible_size(width, height)
        self.tab.emulation.force_viewport()

        # wait for a spell for the page to adjust to its new world
        if settle:
            if after_events is None:
                logging.info('Waiting {}ms for resize to settle'.format(settle))
                time.sleep(settle / 1e3)
            else:
                wfi_params = {}

                if settle_timeout:
                    wfi_params['timeout'] = settle_timeout

                if after_events != 'any':
                    wfi_params['event_filter'] = after_events

                try:
                    logging.info('Waiting {}ms after last events'.format(settle))
                    self.tab.wait_for_idle(settle, **wfi_params)
                except exceptions.TimeoutError:
                    pass

        # setup a FLO to write data to if we don't have one
        if destination is None:
            destination = io.BytesIO()
        elif isinstance(destination, basestring):
            return_flo = False

        self.tab.page.capture_screenshot(destination, format=format)

        out = {
            'element': element,
            'width':   width,
            'height':  height,
        }

        if return_flo:
            destination.seek(0)
            out['destination'] = destination

            if autoclose:
                if hasattr(destination, 'close'):
                    close = getattr(destination, 'close')

                    if callable(close):
                        close()
        else:
            out['path'] = destination

        return out

    def start_capture(
        self,
        destination,
        duration=None,
        format='png',
        jpeg_quality=85,
        every_nth=None,
        filename_format=None
    ):
        self.tab.page.start_screencast(
            destination=destination,
            duration=duration,
            format=format,
            jpeg_quality=jpeg_quality,
            every_nth=every_nth,
            filename_format=filename_format,
            additional_values=self.scope.as_dict()
        )

    def wait_for_capture(self):
        self.tab.wait_for('Page.screencastVisibilityChanged')

    def stop_capture(self):
        self.tab.page.stop_screencast()

    def find(self, text, **kwargs):
        logging.info('text={}, kwargs={}'.format(text, kwargs))
        raise exceptions.NotImplemented("find()")

    def source(self, selector=None):
        if selector:
            elements = self.tab.dom.select_nodes(selector, wait_for_match=True)
            self.tab.dom.ensure_unique_element(selector, elements)
            return elements['nodes'][0].outer_html
        else:
            return self.tab.dom.root.outer_html

    def remove(self, selector):
        removed = []

        for element in self.tab.dom.query_all(selector):
            self.tab.dom.remove(element.id)
            removed.append(element)

        return removed

    def dump_dom(self):
        self.tab.dom.print_node()
