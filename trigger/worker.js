// Runs the "Sync iCal feeds" workflow every 15 minutes. GitHub's own cron in
// sync-ical.yml is a fallback only: measured Oct-Nov 2026 it fired every 2-11 h,
// which is too slow to stop a double booking between Airbnb and Booking.com.
// GITHUB_TOKEN: fine-grained PAT, repo freezer3/atlantic-villa, Actions: read and write.
export default {
  async scheduled(controller, env) {
    const res = await fetch(
      'https://api.github.com/repos/freezer3/atlantic-villa/actions/workflows/sync-ical.yml/dispatches',
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: 'application/vnd.github+json',
          'User-Agent': 'villa-atlantic-trigger',
        },
        body: JSON.stringify({ ref: 'main' }),
      }
    );
    if (!res.ok) throw new Error(`workflow_dispatch failed: ${res.status} ${await res.text()}`);
  },
};
