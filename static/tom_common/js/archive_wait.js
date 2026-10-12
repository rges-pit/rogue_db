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
 * so it's watched for in the requests it makes: it fetches the survey's tiles through window.fetch,
 * named as HiPS names them (.../Norder<k>/...). A wrapper around fetch looks out for the first of
 * those to succeed, and removes itself when it has.
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
    let timer = null;
    let arrived = false;

    function show(text, spinning, warning) {
      box.hidden = false;
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
    }

    function imagesArrived() {
      arrived = true;
      stopWatching();
      box.hidden = true;
    }

    function watchForImages() {
      if (wrapper) return;
      wrapper = function (input) {
        const result = nativeFetch.apply(this, arguments);
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        if (!arrived && TILE_URL.test(url)) {
          result.then(response => { if (response.ok) imagesArrived(); }, () => {});
        }
        return result;
      };
      window.fetch = wrapper;
    }

    return {
      // The wait begins
      waiting: function () {
        arrived = false;
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
            show('The archive is not responding. The image will appear if it does.', true, true);
          }
        }, timeoutMs);
      },

      // Aladin Lite couldn't be loaded or started
      failed: function (text) {
        stopWatching();
        show(text, false, true);
      },
    };
  };
})();
