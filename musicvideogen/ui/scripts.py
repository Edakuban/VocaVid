from __future__ import annotations

SCRIPTS = f"""
    const projectRowServerHtml = new Map();
    let projectStoryboardServerHtml = '';
    function rememberProjectRows() {{
      document.querySelectorAll('tr[id^="line-row-"], tr[id^="segment-row-"]').forEach((row) => {{
        projectRowServerHtml.set(row.id, row.outerHTML);
      }});
    }}
    function rememberProjectStoryboard() {{
      const storyboard = document.getElementById('project-storyboard');
      if (!storyboard) return;
      projectStoryboardServerHtml = storyboard.outerHTML;
    }}
    function copySelectedLines(form) {{
      form.querySelectorAll('input[name="selected_lines"]').forEach((input) => input.remove());
      const selectedSegments = document.querySelectorAll('.segment-select:checked:not(:disabled)');
      const selectedLines = selectedSegments.length ? selectedSegments : document.querySelectorAll('.line-select:checked:not(:disabled)');
      if (!selectedLines.length) {{
        const hasSegments = document.querySelectorAll('.segment-select').length > 0;
        const itemLabel = hasSegments ? 'Segmente' : 'Zeilen';
        if (!confirm('Keine Checkbox markiert. Es werden alle(!) ' + itemLabel + ' verarbeitet. Fortfahren?')) {{
          return false;
        }}
      }}
      selectedLines.forEach((checkbox) => {{
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'selected_lines';
        input.value = checkbox.value;
        form.appendChild(input);
      }});
      return true;
    }}
    function currentProjectId() {{
      const match = window.location.pathname.match(/^\\/projects\\/(\\d+)/);
      return match ? Number(match[1]) : 0;
    }}
    function projectActionSubmitted(form) {{
      if (!copySelectedLines(form)) return false;
      const projectId = currentProjectId();
      if (projectId) {{
        window.setTimeout(() => refreshProjectStatus(projectId), 150);
      }}
      return true;
    }}
    function toggleRowSelection(event, row) {{
      const interactiveSelector = 'button, a, input, textarea, select, label, audio, video, img, form';
      if (event.target.closest(interactiveSelector)) return;
      const checkbox = row.querySelector('.segment-select, .line-select');
      if (!checkbox) return;
      checkbox.checked = !checkbox.checked;
    }}
    function projectRowChanged(row, replacement) {{
      const previousHtml = projectRowServerHtml.get(row.id) || row.outerHTML;
      return previousHtml !== replacement.outerHTML;
    }}
    function replaceProjectRow(row, html) {{
      const checkbox = row.querySelector('.segment-select, .line-select');
      const template = document.createElement('template');
      template.innerHTML = html.trim();
      const replacement = template.content.firstElementChild;
      if (!replacement) return;
      if (!projectRowChanged(row, replacement)) return;
      const replacementCheckbox = replacement.querySelector('.segment-select, .line-select');
      if (checkbox && replacementCheckbox) {{
        replacementCheckbox.checked = checkbox.checked;
      }}
      row.replaceWith(replacement);
      projectRowServerHtml.set(replacement.id, replacement.outerHTML);
    }}
    const projectStoryboardFieldSelector = 'input:not(.storyboard-select), textarea, select';
    function projectStoryboardHasActiveEdit(storyboard) {{
      const active = document.activeElement;
      return !!(active && active.closest && storyboard.contains(active) && active.matches(projectStoryboardFieldSelector));
    }}
    function projectStoryboardFieldDirty(field) {{
      if (field.type === 'checkbox' || field.type === 'radio') {{
        return field.checked !== field.defaultChecked;
      }}
      if (field.tagName === 'SELECT') {{
        return Array.from(field.options).some((option) => option.selected !== option.defaultSelected);
      }}
      return field.value !== field.defaultValue;
    }}
    function projectStoryboardHasDirtyFields(storyboard) {{
      return Array.from(storyboard.querySelectorAll(projectStoryboardFieldSelector)).some(projectStoryboardFieldDirty);
    }}
    function projectStoryboardHasPlayingVideo(storyboard) {{
      return Array.from(storyboard.querySelectorAll('.storyboard-card-video')).some((video) => !video.paused && !video.ended);
    }}
    function projectStoryboardHasOpenPromptModal(storyboard) {{
      return !!storyboard.querySelector('.prompt-modal.open');
    }}
    function shouldReplaceProjectStoryboard(storyboard) {{
      return !projectStoryboardHasActiveEdit(storyboard) && !projectStoryboardHasDirtyFields(storyboard) && !projectStoryboardHasPlayingVideo(storyboard) && !projectStoryboardHasOpenPromptModal(storyboard);
    }}
    function projectStoryboardChanged(storyboard, replacement) {{
      const previousHtml = projectStoryboardServerHtml || storyboard.outerHTML;
      return previousHtml !== replacement.outerHTML;
    }}
    function activeProjectStoryboardTemplateId(storyboard) {{
      const activeCard = storyboard.querySelector('.storyboard-card-active');
      return activeCard ? activeCard.dataset.inspectorTemplate : '';
    }}
    function checkedProjectStoryboardValues(storyboard) {{
      return new Set(Array.from(storyboard.querySelectorAll('.storyboard-select:checked')).map((checkbox) => checkbox.value));
    }}
    function restoreProjectStoryboardCheckedValues(storyboard, values) {{
      storyboard.querySelectorAll('.storyboard-select').forEach((checkbox) => {{
        checkbox.checked = values.has(checkbox.value);
      }});
    }}
    function restoreProjectStoryboardSelection(storyboard, templateId) {{
      if (!templateId) return;
      const card = storyboard.querySelector('[data-inspector-template="' + templateId + '"]');
      if (!card) return;
      selectStoryboardCard(storyboard, card);
    }}
    function replaceProjectStoryboard(html) {{
      const storyboard = document.getElementById('project-storyboard');
      if (!storyboard || html === undefined) return;
      if (!shouldReplaceProjectStoryboard(storyboard)) return;
      const activeTemplateId = activeProjectStoryboardTemplateId(storyboard);
      const checkedValues = checkedProjectStoryboardValues(storyboard);
      const template = document.createElement('template');
      template.innerHTML = html.trim();
      const replacement = template.content.firstElementChild;
      if (!replacement) return;
      if (!projectStoryboardChanged(storyboard, replacement)) return;
      projectStoryboardServerHtml = replacement.outerHTML;
      replacement.hidden = storyboard.hidden;
      storyboard.replaceWith(replacement);
      restoreProjectStoryboardCheckedValues(replacement, checkedValues);
      restoreProjectStoryboardSelection(replacement, activeTemplateId);
    }}
    const baseDocumentTitle = document.title.replace(/^\\(\\d+\\)\\s+/, '');
    function updateBrowserTitle(queueCount) {{
      if (queueCount === undefined || queueCount === null) return;
      const count = Math.max(0, Number(queueCount) || 0);
      document.title = count > 0 ? '(' + count + ') ' + baseDocumentTitle : baseDocumentTitle;
    }}
    function updateProjectStatus(data) {{
      updateQueueEstimate(data.queue_estimate_seconds, data.queue_count);
      updateBrowserTitle(data.queue_count);
      const progress = document.getElementById('project-progress-pill');
      if (progress && data.progress_html !== undefined) progress.outerHTML = data.progress_html;
      Object.entries(data.rows || {{}}).forEach(([rowId, html]) => {{
        const row = document.getElementById(rowId);
        if (row) replaceProjectRow(row, html);
      }});
      if (data.storyboard_html !== undefined) replaceProjectStoryboard(data.storyboard_html);
    }}
    async function refreshProjectStatus(projectId) {{
      if (!projectId) return;
      const response = await fetch('/projects/' + projectId + '/status');
      if (!response.ok) return;
      const data = await response.json();
      updateProjectStatus(data);
    }}
    async function pollProjectStatus(projectId) {{
      try {{
        await refreshProjectStatus(projectId);
      }} catch (error) {{
        return;
      }} finally {{
        window.setTimeout(() => pollProjectStatus(projectId), 2500);
      }}
    }}
    function updateJobsStatus(data) {{
      updateQueueEstimate(data.queue_estimate_seconds, data.queue_count);
      updateBrowserTitle(data.queue_count);
      const queueSummary = document.getElementById('queue-summary');
      if (queueSummary && data.queue_summary_html !== undefined) queueSummary.innerHTML = data.queue_summary_html;
      const jobsBody = document.getElementById('jobs-table-body');
      if (jobsBody && data.jobs_html !== undefined) jobsBody.innerHTML = data.jobs_html;
      const autodelete = document.querySelector('input[name="autodelete_finished"]');
      if (autodelete && data.autodelete_finished !== undefined) autodelete.checked = Boolean(data.autodelete_finished);
      const shutdown = document.querySelector('input[name="shutdown_after_queue"]');
      if (shutdown && data.shutdown_after_queue !== undefined) shutdown.checked = Boolean(data.shutdown_after_queue);
    }}
    async function refreshJobsStatus() {{
      const response = await fetch('/jobs/status');
      if (!response.ok) return;
      updateJobsStatus(await response.json());
    }}
    async function pollJobsStatus() {{
      try {{
        await refreshJobsStatus();
      }} catch (error) {{
        return;
      }} finally {{
        window.setTimeout(pollJobsStatus, 2500);
      }}
    }}
    function formatDuration(seconds) {{
      const total = Math.max(0, Math.round(Number(seconds) || 0));
      const hours = Math.floor(total / 3600);
      const minutes = Math.floor((total % 3600) / 60);
      const remaining = total % 60;
      if (hours) return hours + 'h ' + minutes + 'm';
      if (minutes) return minutes + 'm ' + remaining + 's';
      return remaining + 's';
    }}
    function queueEstimateLabel(seconds, queueCount) {{
      const count = Math.max(0, Number(queueCount) || 0);
      if (count <= 0) return 'Queue 0';
      const value = Math.max(0, Number(seconds) || 0);
      return value > 0 ? count + ' ~' + formatDuration(value) : count + ' ~?s';
    }}
    function updateQueueEstimate(seconds, queueCount) {{
      const elements = document.querySelectorAll('[data-queue-estimate="1"]');
      if (!elements.length || seconds === undefined || seconds === null) return;
      const value = Math.max(0, Number(seconds) || 0);
      const firstElement = elements[0];
      const count = queueCount === undefined || queueCount === null ? Number(firstElement.dataset.count || 0) : Math.max(0, Number(queueCount) || 0);
      elements.forEach((element) => {{
        element.dataset.seconds = String(Math.round(value));
        element.dataset.count = String(Math.round(count));
        element.textContent = queueEstimateLabel(value, count);
      }});
    }}
    function setupQueueEstimateCountdown() {{
      window.setInterval(() => {{
        const element = document.querySelector('[data-queue-estimate="1"]');
        if (!element) return;
        const value = Math.max(0, Number(element.dataset.seconds || 0) - 1);
        updateQueueEstimate(value, Number(element.dataset.count || 0));
      }}, 1000);
    }}
    function openQueueModal() {{
      const box = document.getElementById('queue-modal');
      if (!box) return;
      box.classList.add('open');
      refreshJobsStatus();
    }}
    function closeQueueModal() {{
      const box = document.getElementById('queue-modal');
      if (!box) return;
      box.classList.remove('open');
    }}
    function openNewProjectModal() {{
      const box = document.getElementById('new-project-modal');
      if (!box) return;
      box.classList.add('open');
    }}
    function closeNewProjectModal() {{
      const box = document.getElementById('new-project-modal');
      if (!box) return;
      box.classList.remove('open');
    }}
    function normalizeSearchText(value) {{
      return String(value || '').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');
    }}
    function applyProjectBrowserControls() {{
      const grid = document.getElementById('project-grid');
      if (!grid) return;
      const search = normalizeSearchText(document.getElementById('project-search')?.value || '');
      const filter = document.getElementById('project-filter')?.value || 'all';
      const sort = document.getElementById('project-sort')?.value || 'newest';
      const cards = Array.from(grid.querySelectorAll('.project-card'));
      cards.sort((a, b) => {{
        if (sort === 'oldest') return Number(a.dataset.projectId || 0) - Number(b.dataset.projectId || 0);
        if (sort === 'name-asc') return String(a.dataset.title || '').localeCompare(String(b.dataset.title || ''));
        if (sort === 'name-desc') return String(b.dataset.title || '').localeCompare(String(a.dataset.title || ''));
        return Number(b.dataset.projectId || 0) - Number(a.dataset.projectId || 0);
      }}).forEach((card) => grid.appendChild(card));
      let visible = 0;
      cards.forEach((card) => {{
        const titleMatches = normalizeSearchText(card.dataset.title || '').includes(search);
        const filterMatches = filter === 'all' || card.dataset.status === filter;
        const show = titleMatches && filterMatches;
        card.classList.toggle('project-card-hidden', !show);
        if (show) visible += 1;
      }});
      const empty = document.getElementById('project-empty-state');
      if (empty) empty.classList.toggle('visible', visible === 0);
    }}
    function setupProjectBrowserControls() {{
      ['project-search', 'project-filter', 'project-sort'].forEach((id) => {{
        const element = document.getElementById(id);
        if (!element) return;
        element.addEventListener('input', applyProjectBrowserControls);
        element.addEventListener('change', applyProjectBrowserControls);
      }});
      document.querySelectorAll('.project-card video').forEach((video) => {{
        const card = video.closest('.project-card');
        if (!card) return;
        card.addEventListener('mouseenter', () => {{
          video.muted = true;
          video.play().catch(() => {{}});
        }});
        card.addEventListener('mouseleave', () => {{
          video.pause();
          video.currentTime = 0;
        }});
      }});
      applyProjectBrowserControls();
    }}
    function openProjectSettingsModal() {{
      const box = document.getElementById('project-settings-modal');
      if (!box) return;
      box.classList.add('open');
    }}
    function closeProjectSettingsModal() {{
      const box = document.getElementById('project-settings-modal');
      if (!box) return;
      box.classList.remove('open');
    }}
    function openPromptModal(id) {{
      const box = document.getElementById(id);
      if (!box) return;
      box.classList.add('open');
    }}
    function closePromptModal(id) {{
      const box = document.getElementById(id);
      if (!box) return;
      box.classList.remove('open');
    }}
    function scrollToTop() {{
      const firstSegment = document.querySelector('tr[id^="segment-row-"]');
      const target = firstSegment || document.querySelector('tr[id^="line-row-"]');
      if (!target) {{
        window.scrollTo({{ top: 0, behavior: 'smooth' }});
        return;
      }}
      const topbar = document.querySelector('.project-topbar');
      const offset = topbar ? topbar.getBoundingClientRect().height : 0;
      const top = target.getBoundingClientRect().top + window.scrollY - offset;
      window.scrollTo({{ top: Math.max(0, top), behavior: 'smooth' }});
    }}
    function switchProjectView(view) {{
      const storyboard = document.getElementById('project-storyboard');
      const table = document.getElementById('project-table-view');
      if (!storyboard || !table) return;
      const showTable = view === 'table';
      storyboard.hidden = showTable;
      table.hidden = !showTable;
      document.querySelectorAll('[data-project-view]').forEach((button) => {{
        const active = button.dataset.projectView === view;
        button.classList.toggle('active', active);
        button.setAttribute('aria-pressed', active ? 'true' : 'false');
      }});
    }}
    function selectStoryboardCard(storyboard, card) {{
      const templateId = card.dataset.inspectorTemplate;
      const template = templateId ? document.getElementById(templateId) : null;
      const current = storyboard.querySelector('#segment-inspector');
      if (!template || !current) return;
      storyboard.querySelectorAll('.storyboard-card-active').forEach((item) => item.classList.remove('storyboard-card-active'));
      card.classList.add('storyboard-card-active');
      const fragment = template.content.cloneNode(true);
      const replacement = fragment.querySelector('#segment-inspector');
      if (!replacement) return;
      current.replaceWith(replacement);
    }}
    function selectStoryboardTemplate(templateId) {{
      const storyboard = document.getElementById('project-storyboard');
      if (!storyboard || !templateId) return;
      const card = storyboard.querySelector('[data-inspector-template="' + templateId + '"]');
      if (!card) return;
      selectStoryboardCard(storyboard, card);
    }}
    function selectStoryboardItem(event, card) {{
      const interactiveSelector = 'button, a, input, textarea, select, label, audio, video, img, form';
      if (event && event.target && event.target.closest(interactiveSelector)) return;
      if (card.dataset.locked === '1') return;
      const storyboard = card.closest('#project-storyboard');
      if (!storyboard) return;
      selectStoryboardCard(storyboard, card);
    }}
    function scrollStorageKey() {{
      return 'musicvideogen-scroll:' + window.location.pathname;
    }}
    function storyboardSelectionStorageKey() {{
      return 'musicvideogen-storyboard-selection:' + window.location.pathname;
    }}
    function rememberProjectStoryboardSelection() {{
      const storyboard = document.getElementById('project-storyboard');
      if (!storyboard) return;
      const activeTemplateId = activeProjectStoryboardTemplateId(storyboard);
      if (!activeTemplateId) return;
      sessionStorage.setItem(storyboardSelectionStorageKey(), activeTemplateId);
    }}
    function rememberScrollPosition() {{
      rememberProjectStoryboardSelection();
      sessionStorage.setItem(scrollStorageKey(), String(window.scrollY));
    }}
    function openQueueJobRow(row) {{
      const href = row.dataset.href;
      if (!href) return;
      const templateId = row.dataset.templateId || '';
      if (templateId) {{
        sessionStorage.setItem('musicvideogen-storyboard-selection:' + href, templateId);
      }}
      window.location.href = href;
    }}
    function confirmProjectSettingsSave(form) {{
      rememberScrollPosition();
      return true;
    }}
    document.addEventListener('submit', rememberScrollPosition);
    document.addEventListener('DOMContentLoaded', () => {{
      rememberProjectRows();
      rememberProjectStoryboard();
      setupProjectBrowserControls();
      const storyboard = document.getElementById('project-storyboard');
      const storedStoryboardTemplate = sessionStorage.getItem(storyboardSelectionStorageKey());
      if (storyboard && storedStoryboardTemplate) {{
        restoreProjectStoryboardSelection(storyboard, storedStoryboardTemplate);
      }}
      const stored = sessionStorage.getItem(scrollStorageKey());
      if (stored === null) return;
      const scrollY = Number(stored);
      if (!Number.isFinite(scrollY)) return;
      requestAnimationFrame(() => window.scrollTo(0, scrollY));
    }});
    function toggleAudio(button) {{
      const audio = button.nextElementSibling;
      if (!audio) return;
      if (audio.paused) {{
        audio.play();
        button.textContent = '||';
      }} else {{
        audio.pause();
        button.textContent = '▶';
      }}
      audio.onended = () => {{ button.textContent = '▶'; }};
    }}
    function toggleStoryboardVideo(event, target) {{
      if (event) event.stopPropagation();
      const media = target.closest('.storyboard-card-media-clip');
      if (!media) return;
      const video = media.querySelector('video');
      const button = media.querySelector('.storyboard-video-toggle');
      if (!video) return;
      if (video.paused) {{
        video.play();
        if (button) {{
          button.setAttribute('aria-label', 'Pause clip');
          button.querySelector('.storyboard-play-icon').textContent = 'Ⅱ';
        }}
      }} else {{
        video.pause();
        if (button) {{
          button.setAttribute('aria-label', 'Play clip');
          button.querySelector('.storyboard-play-icon').textContent = '▶';
        }}
      }}
      video.onended = () => {{
        if (!button) return;
        button.setAttribute('aria-label', 'Play clip');
        button.querySelector('.storyboard-play-icon').textContent = '▶';
      }};
    }}
    function resetStoryboardVideo(target) {{
      const media = target && target.closest ? target.closest('.storyboard-card-media-clip') : null;
      if (!media) return;
      const video = media.querySelector('video');
      const button = media.querySelector('.storyboard-video-toggle');
      if (video) {{
        video.pause();
        video.currentTime = 0;
      }}
      if (button) {{
        button.setAttribute('aria-label', 'Play clip');
        button.querySelector('.storyboard-play-icon').textContent = '▶';
      }}
    }}
    function openClipLightbox(src, source) {{
      resetStoryboardVideo(source);
      const box = document.getElementById('clip-lightbox');
      const video = document.getElementById('clip-lightbox-video');
      video.src = src;
      box.classList.add('open');
      video.play();
    }}
    function closeClipLightbox() {{
      const box = document.getElementById('clip-lightbox');
      const video = document.getElementById('clip-lightbox-video');
      video.pause();
      video.removeAttribute('src');
      video.load();
      box.classList.remove('open');
    }}
    function openImageLightbox(src) {{
      const box = document.getElementById('image-lightbox');
      const image = document.getElementById('image-lightbox-image');
      image.src = src;
      box.classList.add('open');
    }}
    function closeImageLightbox() {{
      const box = document.getElementById('image-lightbox');
      const image = document.getElementById('image-lightbox-image');
      image.removeAttribute('src');
      box.classList.remove('open');
    }}
"""
