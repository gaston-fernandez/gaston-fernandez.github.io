(function () {
  const badges = Array.from(
    document.querySelectorAll('.scholar-citation-badge[data-citation-key]')
  );
  if (!badges.length) {
    return;
  }

  const DEFAULT_PROFILE_URL =
    'https://scholar.google.com/citations?user=I0oFwVgAAAAJ&hl=en&oi=ao';

  function clearBadge(badge) {
    while (badge.firstChild) {
      badge.removeChild(badge.firstChild);
    }
  }

  function setBadgeText(badge, text, stateClass) {
    clearBadge(badge);
    const chip = document.createElement('span');
    chip.className = 'scholar-citation-chip';
    if (stateClass) {
      chip.classList.add(stateClass);
    }
    chip.textContent = text;
    badge.appendChild(chip);
  }

  function isScholarUrl(url) {
    return typeof url === 'string' && /^https:\/\/scholar\.google\.com\//i.test(url);
  }

  function toDisplayDate(isoDate) {
    if (!isoDate) {
      return '';
    }
    const parsed = new Date(isoDate);
    if (Number.isNaN(parsed.getTime())) {
      return '';
    }
    return parsed.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  }

  function setBadgeCount(badge, publication, updatedAt, fallbackProfileUrl) {
    const count = publication && Number.isFinite(publication.citations)
      ? publication.citations
      : null;

    if (count === null) {
      setBadgeText(badge, 'Citations unavailable', 'is-unavailable');
      return;
    }

    clearBadge(badge);

    const link = document.createElement('a');
    link.className = 'scholar-citation-link';
    link.target = '_blank';
    link.rel = 'noopener noreferrer';

    const resolvedUrl = isScholarUrl(publication && publication.scholar_url)
      ? publication.scholar_url
      : fallbackProfileUrl;
    link.href = resolvedUrl;

    const chip = document.createElement('span');
    chip.className = 'scholar-citation-chip';
    chip.textContent = 'Cited by ' + count;

    if (updatedAt) {
      chip.title = 'Google Scholar citations, updated ' + updatedAt;
    }

    link.appendChild(chip);
    badge.appendChild(link);
  }

  badges.forEach((badge) => {
    setBadgeText(badge, 'Loading citations...', 'is-loading');
  });

  fetch('/data/scholar_citations.json', { cache: 'no-store' })
    .then((response) => {
      if (!response.ok) {
        throw new Error('Failed to load citation data: ' + response.status);
      }
      return response.json();
    })
    .then((payload) => {
      const publications = payload && payload.publications ? payload.publications : {};
      const updatedAt = toDisplayDate(payload && payload.updated_at);
      const fallbackProfileUrl = isScholarUrl(payload && payload.profile_url)
        ? payload.profile_url
        : DEFAULT_PROFILE_URL;

      badges.forEach((badge) => {
        const key = badge.getAttribute('data-citation-key');
        const publication = key ? publications[key] : null;
        setBadgeCount(badge, publication, updatedAt, fallbackProfileUrl);
      });
    })
    .catch(function () {
      badges.forEach((badge) => {
        setBadgeText(badge, 'Citations unavailable', 'is-unavailable');
      });
    });
})();
