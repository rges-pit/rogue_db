/*
 * Site-wide terminology relabeling: this TOM's users refer to "Targets" as
 * "Sources". Rather than forking every tom_base template that mentions
 * "Target" (there are dozens, none of which wrap the word in {% trans %}, so
 * there's no clean Django-level hook), this rewrites the rendered text in
 * the browser. The underlying models, URLs, field names, and IDs are never
 * touched -- only what's visibly displayed to the user.
 */
(function () {
    'use strict';

    const REPLACEMENTS = [
        [/\bTARGETS\b/g, 'SOURCES'],
        [/\bTargets\b/g, 'Sources'],
        [/\btargets\b/g, 'sources'],
        [/\bTARGET\b/g, 'SOURCE'],
        [/\bTarget\b/g, 'Source'],
        [/\btarget\b/g, 'source'],
    ];

    // Don't touch the contents of these -- form field values are user data,
    // not display chrome, and script/style contents aren't text a user reads.
    const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'INPUT', 'CODE', 'PRE']);

    // Attributes that hold user-visible text (tooltips, placeholders) rather
    // than functional identifiers (href, name, id are left untouched).
    const RELABEL_ATTRS = ['title', 'placeholder', 'aria-label'];

    function relabelText(text) {
        let result = text;
        for (const [pattern, replacement] of REPLACEMENTS) {
            result = result.replace(pattern, replacement);
        }
        return result;
    }

    function relabelTextNodes(root) {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
            acceptNode(node) {
                const parentTag = node.parentElement ? node.parentElement.tagName : '';
                return SKIP_TAGS.has(parentTag) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
            }
        });

        const nodes = [];
        let node;
        while ((node = walker.nextNode())) nodes.push(node);

        for (const textNode of nodes) {
            const relabeled = relabelText(textNode.nodeValue);
            if (relabeled !== textNode.nodeValue) textNode.nodeValue = relabeled;
        }
    }

    function relabelAttributes(root) {
        if (!root.querySelectorAll) return;
        for (const el of root.querySelectorAll('*')) {
            for (const attr of RELABEL_ATTRS) {
                if (el.hasAttribute(attr)) {
                    const value = el.getAttribute(attr);
                    const relabeled = relabelText(value);
                    if (relabeled !== value) el.setAttribute(attr, relabeled);
                }
            }
        }
    }

    function relabel(root) {
        relabelTextNodes(root);
        relabelAttributes(root);
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.title = relabelText(document.title);
        relabel(document.body);
    });

    // HTMX swaps in new content (search results, pagination, sorted tables)
    // without a full page load, so DOMContentLoaded alone won't catch it.
    // Deliberately re-scan document.body rather than evt.detail.target: for
    // an outerHTML swap (used throughout this app's tables), detail.target
    // is the *old*, already-detached element being replaced, not the new
    // live one -- relabeling it has no visible effect. document.body is
    // always the live, connected element regardless of swap type.
    document.body.addEventListener('htmx:afterSwap', function () {
        relabel(document.body);
    });
    document.body.addEventListener('htmx:afterSettle', function () {
        relabel(document.body);
    });
})();
