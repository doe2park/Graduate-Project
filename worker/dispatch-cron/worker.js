// Cloudflare Worker: triggers GitHub Actions workflow_dispatch on a cron.
// GitHub's own `schedule` trigger is heavily throttled on public repos; this
// fires reliably every 15 minutes. Stateless; no public endpoints.

const REPO = 'doe2park/Graduate-Project';
const REF = 'main';
const RETRY_DELAY_MS = 3000;

// event.cron (must match wrangler.toml exactly) -> workflow file
const WORKFLOWS = {
  '*/15 * * * *': 'bmo-campus-energy.yml',
  '7,22,37,52 * * * *': 'bmo-fetch.yml', // Grimes, offset to keep the existing stagger
};

async function dispatchOnce(workflow, token) {
  const url = `https://api.github.com/repos/${REPO}/actions/workflows/${workflow}/dispatches`;
  return fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'graduate-project-dispatch-cron',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ref: REF }),
  });
}

async function dispatch(workflow, token) {
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const res = await dispatchOnce(workflow, token);
      if (res.status === 204) return true;
      const body = (await res.text()).slice(0, 200);
      console.error(`dispatch ${workflow} attempt ${attempt}: HTTP ${res.status} ${body}`);
    } catch (err) {
      console.error(`dispatch ${workflow} attempt ${attempt}: ${err && err.message ? err.message : err}`);
    }
    if (attempt === 1) await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
  }
  return false;
}

export default {
  async scheduled(controller, env, ctx) {
    if (!env || !env.GITHUB_TOKEN) {
      console.error('GITHUB_TOKEN secret is not set; skipping dispatch');
      return;
    }
    const workflow = WORKFLOWS[controller.cron];
    if (!workflow) {
      console.error(`No workflow mapped for cron "${controller.cron}"`);
      return;
    }
    await dispatch(workflow, env.GITHUB_TOKEN);
  },

  // No public trigger endpoint.
  async fetch() {
    return new Response('Not found', { status: 404 });
  },
};
