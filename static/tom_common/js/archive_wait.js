/*
 * The "Waiting for archive..." box shown with Aladin Lite sky views.
 *
 * Aladin Lite, and the survey images it shows, come from servers in Strasbourg, which can be slow or
 * not answer at all. While they are waited for, a box with a spinner says so, so that it's clear the
 * wait isn't this site's. It's shown by:
 *   - the Imaging tab of a source (target_detail.html), and
 *   - the skymap of the target list (partials/aladin_skymap.html).
 *
 * The box is an element with a spinner (.spinner-border) and a message (.archive-wait-message):
 *
 *   const wait = ArchiveWait(document.getElementById('archive-wait'));
 *   wait.waiting();          // start of the wait: shows the box
 *   ...load Aladin Lite, start the view...
 *   wait.loaded();           // Aladin Lite is up: the survey images are being waited for
 *   wait.failed('...');      // or: it couldn't be loaded
 *
 * The box goes by itself when the first survey image has come back. Aladin Lite has no event for that,
 * so it's watched for in the requests it makes. Its survey images are named as HiPS names them
 * (.../Norder<k>/...), and are looked out for in two ways, either of which will do, as which way
 * Aladin Lite loads a picture (fetch, or an <img>) can differ, with the picture and the browser:
 *   - a wrapper around window.fetch, which sees a fetch of one succeed, and
 *   - the browser's own record of the resources the page has loaded (Resource Timing), which has
 *     every image or fetch that has finished, whichever way it was made.
 * Both are removed when the first has been seen.
 *
 * What it sees, and does, is written to the browser's console (at the debug level, which some
 * browsers hide unless it's asked for), to say why the box is still there if it is.
 */
(function () {
  'use strict';

  const TILE_URL = /\/Norder\d+\//;

  window.ArchiveWait = function (box, options) {
    options = options || {};
    // How long to wait for the first image before saying the archive isn't responding
    const timeoutMs = options.timeoutMs || 30000;

    const message = box.querySelector('.archive-wait-message');
    const spinner = box.querySelector('.spinner-border');
    const nativeFetch = window.fetch;
    let wrapper = null;
    let observer = null;
    let timer = null;
    let arrived = false;

    function log() {
      console.debug.apply(console, ['[archive-wait]'].concat(Array.prototype.slice.call(arguments)));
    }

    // Showing and hiding the box. Hiding needs more than the hidden attribute: the box is a Bootstrap d-flex,
    // which is display:flex !important, and that beats the [hidden] rule (display:none !important) of the same
    // weight that comes before it in Bootstrap's stylesheet. So the box stayed on the page after it was
    // "hidden". An !important of the inline style is the one that beats a class's.
    function setHidden(hidden) {
      box.hidden = hidden;
      if (hidden) {
        box.style.setProperty('display', 'none', 'important');
      } else {
        box.style.removeProperty('display');
      }
    }

    function show(text, spinning, warning) {
      setHidden(false);
      spinner.hidden = !spinning;
      message.textContent = text;
      message.classList.toggle('text-warning', warning);
    }

    function stopWatching() {
      clearTimeout(timer);
      // Only if it's still ours that's there, in case something else has wrapped fetch since
      if (wrapper && window.fetch === wrapper) {
        window.fetch = nativeFetch;
      }
      wrapper = null;
      if (observer) {
        observer.disconnect();
        observer = null;
      }
    }

    function imagesArrived(how, url) {
      if (arrived) return;
      arrived = true;
      log('survey image arrived (' + how + '): ' + url);
      stopWatching();
      setHidden(true);
    }

    function watchForImages() {
      if (!wrapper) {
        wrapper = function (input) {
          const result = nativeFetch.apply(this, arguments);
          const url = typeof input === 'string' ? input : (input && input.url) || '';
          if (!arrived && TILE_URL.test(url)) {
            result.then(
              response => {
                if (response.ok) {
                  imagesArrived('fetch', url);
                } else {
                  log('survey image fetch failed: HTTP ' + response.status + ' ' + url);
                }
              },
              error => log('survey image fetch failed: ' + error + ' ' + url)
            );
          }
          return result;
        };
        window.fetch = wrapper;
      }

      // The browser's record of what has finished loading. An entry has the status of the response where the
      // browser says (an error is not an image), and is taken to be one that came if it doesn't.
      if (!observer && typeof PerformanceObserver !== 'undefined') {
        try {
          observer = new PerformanceObserver(function (list) {
            list.getEntries().forEach(function (entry) {
              if (arrived || !TILE_URL.test(entry.name)) return;
              if (entry.responseStatus >= 400) {
                log('survey image resource failed: HTTP ' + entry.responseStatus + ' ' + entry.name);
              } else {
                imagesArrived('resource, ' + entry.initiatorType, entry.name);
              }
            });
          });
          observer.observe({type: 'resource'});
        } catch (error) {
          log('resource timing not available: ' + error);
          observer = null;
        }
      }
    }

    return {
      // The wait begins
      waiting: function () {
        arrived = false;
        log('waiting for the archive');
        show('Waiting for archive...', true, false);
        watchForImages();
      },

      // Aladin Lite is up and has started asking for images. If none has come after a while, say that
      // the archive isn't responding; the box still goes if one arrives after all.
      loaded: function () {
        if (arrived) return;
        clearTimeout(timer);
        timer = setTimeout(function () {
          if (!arrived) {
            log('no survey image after ' + timeoutMs / 1000 + ' s');
            show('The archive is not responding. The image will appear if it does.', true, true);
          }
        }, timeoutMs);
      },

      // Aladin Lite couldn't be loaded or started
      failed: function (text) {
        log('failed: ' + text);
        stopWatching();
        show(text, false, true);
      },
    };
  };
})();
