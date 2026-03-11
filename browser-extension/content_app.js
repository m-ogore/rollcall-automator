/**
 * content_app.js — Roll Call Automator Content Script (Web App page)
 *
 * Injected into the Roll Call Automator web app page.
 * Reads the extension's client_id from chrome.storage and posts it to the
 * page via window.postMessage so app.js can include it in API requests.
 */

chrome.storage.local.get(['client_id'], (result) => {
  if (result.client_id) {
    window.postMessage(
      { type: 'ROLLCALL_AGENT_ID', client_id: result.client_id },
      '*'
    );
  }
});
