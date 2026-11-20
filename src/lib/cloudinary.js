// Сүрөт жүктөө: Cloudinary (unsigned preset). Конфиг жок болсо — кысылган base64.
const CLOUD = import.meta.env.VITE_CLOUDINARY_CLOUD_NAME;
const PRESET = import.meta.env.VITE_CLOUDINARY_UPLOAD_PRESET;
export const cloudinaryEnabled = Boolean(CLOUD && PRESET);

function compress(file, max = 800) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = reject;
    reader.onload = () => {
      const img = new Image();
      img.onerror = reject;
      img.onload = () => {
        const scale = Math.min(1, max / Math.max(img.width, img.height));
        const c = document.createElement('canvas');
        c.width = Math.round(img.width * scale);
        c.height = Math.round(img.height * scale);
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        resolve(c.toDataURL('image/jpeg', 0.8));
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

export async function uploadImage(file, onProgress) {
  if (!file || !file.type.startsWith('image/')) throw new Error('not-image');
  if (file.size > 10 * 1024 * 1024) throw new Error('too-large');
  if (!cloudinaryEnabled) {
    onProgress?.(100);
    return compress(file);
  }
  return new Promise((resolve, reject) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('upload_preset', PRESET);
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `https://api.cloudinary.com/v1_1/${CLOUD}/image/upload`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(Math.round((e.loaded / e.total) * 100));
    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status < 300 && data.secure_url) resolve(data.secure_url);
        else reject(new Error(data.error?.message || 'upload-failed'));
      } catch {
        reject(new Error('upload-failed'));
      }
    };
    xhr.onerror = () => reject(new Error('upload-failed'));
    xhr.send(fd);
  });
}
