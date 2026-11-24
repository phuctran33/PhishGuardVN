import { backendOrigin, CheckError, DEFAULT_BACKEND, hostPermission } from './prediction.mjs';

const form = document.getElementById('settings');
const input = document.getElementById('backend');
const feedback = document.getElementById('feedback');
const save = document.getElementById('save');
const defaultPermission = hostPermission(DEFAULT_BACKEND);

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  save.disabled = true;
  feedback.textContent = '';
  try {
    const backend = backendOrigin(input.value);
    const permission = hostPermission(backend);
    // Chrome requires optional host access to be granted from a user gesture.
    if (permission !== defaultPermission &&
        !await chrome.permissions.request({ origins: [permission] })) {
      throw new CheckError('PERMISSION_DENIED', 'Chưa cấp quyền truy cập địa chỉ backend mới.');
    }
    await chrome.storage.local.set({ backend });
    const { origins = [] } = await chrome.permissions.getAll();
    const old = origins.filter(origin => origin !== permission && origin !== defaultPermission);
    if (old.length) await chrome.permissions.remove({ origins: old });
    input.value = backend;
    feedback.textContent = 'Đã lưu địa chỉ backend.';
  } catch (error) {
    feedback.textContent = error instanceof CheckError ? error.message : 'Không thể lưu cấu hình.';
  } finally {
    save.disabled = false;
  }
});
try {
  const { backend } = await chrome.storage.local.get({ backend: DEFAULT_BACKEND });
  input.value = backend;
} catch {
  feedback.textContent = 'Không thể đọc cấu hình đã lưu.';
}
