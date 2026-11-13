// VeriCloud frontend config.
// infrastructure/setup_api.sh fills in VERICLOUD_API with the vericloud-api function URL.
// Empty = demo mode (no upload, no real check). Never put AWS keys in this file.
const VERICLOUD_API = '';

window.VERICLOUD = !VERICLOUD_API ? { mode: 'demo', adapter: null } : {
  mode: 'live',
  adapter: {
    async createApplication({ application_id, id_card_extension, selfie_extension }) {
      const r = await fetch(VERICLOUD_API + '/applications', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ application_id, id_card_extension, selfie_extension }),
        signal: AbortSignal.timeout(15000),
      });
      if (!r.ok) throw new Error('无法创建申请（' + r.status + '），请稍后再试。');
      return r.json(); // {id_card_url, selfie_url, ...}
    },
    async getResult({ application_id }) {
      const r = await fetch(VERICLOUD_API + '/applications/' + encodeURIComponent(application_id), {
        signal: AbortSignal.timeout(10000),
      });
      if (r.status === 404) return null; // still processing
      if (!r.ok) throw new Error('查询结果失败（' + r.status + '）。');
      return r.json(); // {review_status, reason, processed_at}
    },
  },
};
