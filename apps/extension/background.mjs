const menuId = 'phishguard-check-link';
const resultUrl = chrome.runtime.getURL('result.html');
const selected = new Map();

chrome.runtime.onInstalled.addListener(() => {
  // Updates can retain the previous menu item.
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: menuId,
      title: 'Kiểm tra bằng PhishGuardVN',
      contexts: ['link'],
    });
  });
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  if (info.menuItemId !== menuId || typeof info.linkUrl !== 'string') return;
  const id = crypto.randomUUID();
  selected.set(id, info.linkUrl);
  // This worker's volatile handoff is consumed once by the results page.
  setTimeout(() => selected.delete(id), 20_000);
  try {
    await chrome.windows.create({
      url: resultUrl + '#' + id,
      type: 'popup',
      width: 480,
      height: 620,
      focused: true,
    });
  } catch {
    selected.delete(id);
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== 'take-link' || typeof message.id !== 'string' ||
      sender.id !== chrome.runtime.id ||
      sender.url?.split('#')[0] !== resultUrl) return;
  const url = selected.get(message.id);
  selected.delete(message.id);
  sendResponse(url ?? null);
});
