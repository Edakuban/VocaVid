from __future__ import annotations

SCRIPTS = f"""
    const projectRowServerHtml = new Map();
    let projectStoryboardServerHtml = '';
    const projectStoryboardCardServerHtml = new Map();
    const projectStoryboardTemplateServerHtml = new Map();
    let reelsUploadInteractionUntil = 0;
    let finalizeItems = [];
    let finalizeItemCursor = 0;
    let finalizeCountdownTimer = null;
    let finalizeCountdownValue = 3;
    let finalizeMode = 'closed';
    function rememberProjectRows() {{
      document.querySelectorAll('tr[id^="line-row-"], tr[id^="segment-row-"]').forEach((row) => {{
        projectRowServerHtml.set(row.id, row.outerHTML);
      }});
    }}
    function rememberProjectStoryboard() {{
      const storyboard = document.getElementById('project-storyboard');
      if (!storyboard) return;
      projectStoryboardServerHtml = storyboard.outerHTML;
      projectStoryboardCardServerHtml.clear();
      projectStoryboardTemplateServerHtml.clear();
      storyboard.querySelectorAll('.storyboard-card[data-inspector-template]').forEach((card) => {{
        projectStoryboardCardServerHtml.set(card.dataset.inspectorTemplate, card.outerHTML);
      }});
      storyboard.querySelectorAll('template[id^="segment-inspector-template-"]').forEach((template) => {{
        projectStoryboardTemplateServerHtml.set(template.id, template.outerHTML);
      }});
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
    function storyboardElementIds(root, selector, keyFn) {{
      return Array.from(root.querySelectorAll(selector)).map(keyFn).filter(Boolean);
    }}
    function sameStoryboardElementIds(current, replacement, selector, keyFn) {{
      const currentIds = storyboardElementIds(current, selector, keyFn);
      const replacementIds = storyboardElementIds(replacement, selector, keyFn);
      return currentIds.length === replacementIds.length && currentIds.every((id, index) => id === replacementIds[index]);
    }}
    function storyboardCanPatchInPlace(storyboard, replacement) {{
      if (!storyboard.querySelector('.storyboard-workspace') || !replacement.querySelector('.storyboard-workspace')) return false;
      return (
        sameStoryboardElementIds(storyboard, replacement, '.storyboard-card[data-inspector-template]', (card) => card.dataset.inspectorTemplate) &&
        sameStoryboardElementIds(storyboard, replacement, 'template[id^="segment-inspector-template-"]', (template) => template.id)
      );
    }}
    function directStoryboardChild(parent, selector) {{
      return Array.from(parent.children).find((child) => child.matches && child.matches(selector)) || null;
    }}
    function storyboardMediaKey(media) {{
      if (!media) return '';
      const video = media.querySelector('video');
      if (video) return 'video:' + (video.getAttribute('src') || '') + ':ok=' + String(!!media.querySelector('.storyboard-ok-badge'));
      const image = media.querySelector('img');
      if (image) return 'image:' + (image.getAttribute('src') || '') + ':ok=' + String(!!media.querySelector('.storyboard-ok-badge'));
      return 'empty:' + media.className + ':ok=' + String(!!media.querySelector('.storyboard-ok-badge'));
    }}
    function storyboardMediaEquivalent(currentMedia, replacementMedia) {{
      return storyboardMediaKey(currentMedia) === storyboardMediaKey(replacementMedia);
    }}
    function replaceStoryboardCardChildIfChanged(currentCard, replacementCard, selector) {{
      const currentChild = directStoryboardChild(currentCard, selector);
      const replacementChild = directStoryboardChild(replacementCard, selector);
      if (!currentChild && replacementChild) {{
        currentCard.appendChild(replacementChild);
      }} else if (currentChild && !replacementChild) {{
        currentChild.remove();
      }} else if (selector === '.storyboard-card-media' && storyboardMediaEquivalent(currentChild, replacementChild)) {{
        return;
      }} else if (currentChild && replacementChild && currentChild.outerHTML !== replacementChild.outerHTML) {{
        currentChild.replaceWith(replacementChild);
      }}
    }}
    function copyStoryboardCardAttributes(currentCard, replacementCard) {{
      Array.from(currentCard.attributes).forEach((attribute) => {{
        if (!replacementCard.hasAttribute(attribute.name)) currentCard.removeAttribute(attribute.name);
      }});
      Array.from(replacementCard.attributes).forEach((attribute) => {{
        currentCard.setAttribute(attribute.name, attribute.value);
      }});
    }}
    function patchStoryboardCard(currentCard, replacementCard) {{
      const wasActive = currentCard.classList.contains('storyboard-card-active');
      const currentCheckbox = currentCard.querySelector('.storyboard-select');
      const wasChecked = !!(currentCheckbox && currentCheckbox.checked);
      copyStoryboardCardAttributes(currentCard, replacementCard);
      currentCard.classList.toggle('storyboard-card-active', wasActive);
      replaceStoryboardCardChildIfChanged(currentCard, replacementCard, '.storyboard-select-wrap');
      const replacementCheckbox = currentCard.querySelector('.storyboard-select');
      if (replacementCheckbox) replacementCheckbox.checked = wasChecked;
      replaceStoryboardCardChildIfChanged(currentCard, replacementCard, '.storyboard-card-media');
      replaceStoryboardCardChildIfChanged(currentCard, replacementCard, '.storyboard-card-body');
      replaceStoryboardCardChildIfChanged(currentCard, replacementCard, '.storyboard-lock-overlay');
    }}
    function patchChangedStoryboardCards(storyboard, replacement) {{
      replacement.querySelectorAll('.storyboard-card[data-inspector-template]').forEach((replacementCard) => {{
        const templateId = replacementCard.dataset.inspectorTemplate;
        const currentCard = storyboard.querySelector('[data-inspector-template="' + templateId + '"]');
        if (!currentCard) return;
        const previousHtml = projectStoryboardCardServerHtml.get(templateId) || currentCard.outerHTML;
        projectStoryboardCardServerHtml.set(templateId, replacementCard.outerHTML);
        if (previousHtml === replacementCard.outerHTML) return;
        patchStoryboardCard(currentCard, replacementCard);
      }});
    }}
    function replaceChangedStoryboardTemplates(storyboard, replacement) {{
      let activeTemplateChanged = false;
      const activeTemplateId = activeProjectStoryboardTemplateId(storyboard);
      replacement.querySelectorAll('template[id^="segment-inspector-template-"]').forEach((replacementTemplate) => {{
        const currentTemplate = storyboard.querySelector('template#' + CSS.escape(replacementTemplate.id));
        if (!currentTemplate) return;
        const previousHtml = projectStoryboardTemplateServerHtml.get(replacementTemplate.id) || currentTemplate.outerHTML;
        projectStoryboardTemplateServerHtml.set(replacementTemplate.id, replacementTemplate.outerHTML);
        if (previousHtml === replacementTemplate.outerHTML) return;
        if (replacementTemplate.id === activeTemplateId) activeTemplateChanged = true;
        currentTemplate.replaceWith(replacementTemplate);
      }});
      return activeTemplateChanged;
    }}
    function refreshActiveStoryboardInspector(storyboard) {{
      const activeTemplateId = activeProjectStoryboardTemplateId(storyboard);
      if (!activeTemplateId) return;
      selectStoryboardTemplate(activeTemplateId);
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
    function inspectorWidthStorageKey() {{
      return 'VocaVid-segment-inspector-width';
    }}
    function segmentInspectorWorkspace() {{
      return document.querySelector('#project-storyboard .storyboard-workspace');
    }}
    function clampSegmentInspectorWidth(workspace, width) {{
      const workspaceWidth = workspace.getBoundingClientRect().width;
      const minWidth = 360;
      const maxWidth = Math.max(minWidth, Math.min(920, workspaceWidth - 260));
      return Math.min(Math.max(width, minWidth), maxWidth);
    }}
    function setSegmentInspectorWidth(width, persist) {{
      const workspace = segmentInspectorWorkspace();
      if (!workspace) return;
      const nextWidth = clampSegmentInspectorWidth(workspace, width);
      workspace.style.setProperty('--segment-inspector-width', nextWidth + 'px');
      if (persist) sessionStorage.setItem(inspectorWidthStorageKey(), String(Math.round(nextWidth)));
    }}
    function restoreSegmentInspectorWidth() {{
      const stored = sessionStorage.getItem(inspectorWidthStorageKey());
      if (stored === null) return;
      const width = Number(stored);
      if (Number.isFinite(width)) setSegmentInspectorWidth(width, false);
    }}
    function beginSegmentInspectorResize(event, handle) {{
      const workspace = handle.closest('.storyboard-workspace');
      if (!workspace || event.button !== 0) return;
      event.preventDefault();
      handle.setPointerCapture(event.pointerId);
      workspace.classList.add('storyboard-workspace-resizing');
      const resize = (moveEvent) => {{
        const rect = workspace.getBoundingClientRect();
        setSegmentInspectorWidth(rect.right - moveEvent.clientX, true);
      }};
      const stop = () => {{
        workspace.classList.remove('storyboard-workspace-resizing');
        handle.removeEventListener('pointermove', resize);
        handle.removeEventListener('pointerup', stop);
        handle.removeEventListener('pointercancel', stop);
      }};
      handle.addEventListener('pointermove', resize);
      handle.addEventListener('pointerup', stop);
      handle.addEventListener('pointercancel', stop);
    }}
    function replaceProjectStoryboard(html, force = false) {{
      const storyboard = document.getElementById('project-storyboard');
      if (!storyboard || html === undefined) return;
      if (!force && !shouldReplaceProjectStoryboard(storyboard)) return;
      const template = document.createElement('template');
      template.innerHTML = html.trim();
      const replacement = template.content.firstElementChild;
      if (!replacement) return;
      if (!projectStoryboardChanged(storyboard, replacement)) return;
      const replacementHtml = replacement.outerHTML;
      if (storyboardCanPatchInPlace(storyboard, replacement)) {{
        const activeTemplateChanged = replaceChangedStoryboardTemplates(storyboard, replacement);
        patchChangedStoryboardCards(storyboard, replacement);
        projectStoryboardServerHtml = replacementHtml;
        if (activeTemplateChanged) refreshActiveStoryboardInspector(storyboard);
        restoreSegmentInspectorWidth();
        return;
      }}
      const activeTemplateId = activeProjectStoryboardTemplateId(storyboard);
      const checkedValues = checkedProjectStoryboardValues(storyboard);
      projectStoryboardServerHtml = replacementHtml;
      replacement.hidden = storyboard.hidden;
      storyboard.replaceWith(replacement);
      rememberProjectStoryboard();
      restoreProjectStoryboardCheckedValues(replacement, checkedValues);
      restoreProjectStoryboardSelection(replacement, activeTemplateId);
      restoreSegmentInspectorWidth();
    }}
    const baseDocumentTitle = document.title.replace(/^\\(\\d+\\)\\s+/, '');
    function updateBrowserTitle(queueCount) {{
      if (queueCount === undefined || queueCount === null) return;
      const count = Math.max(0, Number(queueCount) || 0);
      document.title = count > 0 ? '(' + count + ') ' + baseDocumentTitle : baseDocumentTitle;
    }}
    function progressState(progress) {{
      if (!progress) return {{ approved: 0, total: 0, done: false }};
      const approved = Math.max(0, Number(progress.dataset.approved) || 0);
      const total = Math.max(0, Number(progress.dataset.total) || 0);
      return {{ approved, total, done: total > 0 && approved >= total }};
    }}
    function progressFromHtml(html) {{
      const template = document.createElement('template');
      template.innerHTML = html || '';
      return template.content.firstElementChild;
    }}
    function launchProjectCompletionCelebration(progress) {{
      const layer = document.getElementById('project-completion-celebration');
      if (!layer || !progress || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      layer.innerHTML = '';
      layer.classList.remove('project-completion-celebration-active');
      progress.classList.remove('progress-pill-completed');
      const progressRect = progress.getBoundingClientRect();
      layer.style.setProperty('--origin-x', (progressRect.left + progressRect.width / 2) + 'px');
      layer.style.setProperty('--origin-y', (progressRect.top + progressRect.height / 2) + 'px');
      const colors = ['#29d3b0', '#4ce2c2', '#e9489f', '#f15bad', '#f2f5f6'];
      const shapes = ['star', 'dot', 'strip', 'streamer'];
      const count = 76;
      for (let index = 0; index < count; index += 1) {{
        const particle = document.createElement('span');
        const shape = shapes[index % shapes.length];
        const angle = (Math.PI * 2 * index) / count + (Math.random() - .5) * .62;
        const distance = 110 + Math.random() * 430;
        particle.className = 'completion-particle completion-particle-' + shape;
        particle.style.setProperty('--x', (Math.cos(angle) * distance) + 'px');
        particle.style.setProperty('--y', (Math.sin(angle) * distance - Math.random() * 120) + 'px');
        particle.style.setProperty('--r', (Math.random() * 720 - 360) + 'deg');
        particle.style.setProperty('--s', (.62 + Math.random() * 1.2).toFixed(2));
        particle.style.setProperty('--delay', (Math.random() * 190).toFixed(0) + 'ms');
        particle.style.setProperty('--color', colors[index % colors.length]);
        layer.appendChild(particle);
      }}
      const confettiCount = 116;
      for (let index = 0; index < confettiCount; index += 1) {{
        const confetti = document.createElement('span');
        confetti.className = 'completion-confetti';
        confetti.style.setProperty('--left', (Math.random() * 100).toFixed(2) + 'vw');
        confetti.style.setProperty('--fall', (72 + Math.random() * 42).toFixed(2) + 'vh');
        confetti.style.setProperty('--drift', ((Math.random() - .5) * 160).toFixed(1) + 'px');
        confetti.style.setProperty('--r', (Math.random() * 900 - 450).toFixed(0) + 'deg');
        confetti.style.setProperty('--s', (.66 + Math.random() * .72).toFixed(2));
        confetti.style.setProperty('--delay', (Math.random() * 520).toFixed(0) + 'ms');
        confetti.style.setProperty('--duration', (5200 + Math.random() * 1000).toFixed(0) + 'ms');
        confetti.style.setProperty('--color', colors[index % colors.length]);
        layer.appendChild(confetti);
      }}
      progress.classList.add('progress-pill-completed');
      requestAnimationFrame(() => layer.classList.add('project-completion-celebration-active'));
      window.setTimeout(() => {{
        layer.classList.remove('project-completion-celebration-active');
        progress.classList.remove('progress-pill-completed');
        layer.innerHTML = '';
      }}, 6800);
    }}
    function progressCompletionStorageKey() {{
      return 'VocaVid-progress-before-approval:' + window.location.pathname;
    }}
    function rememberApprovalProgressBeforeSubmit() {{
      const progress = document.getElementById('project-progress-pill');
      if (!progress) return;
      sessionStorage.setItem(progressCompletionStorageKey(), JSON.stringify(progressState(progress)));
    }}
    function launchStoredProjectCompletionCelebration() {{
      const stored = sessionStorage.getItem(progressCompletionStorageKey());
      if (stored === null) return;
      sessionStorage.removeItem(progressCompletionStorageKey());
      const progress = document.getElementById('project-progress-pill');
      if (!progress) return;
      try {{
        const previousState = JSON.parse(stored);
        const nextState = progressState(progress);
        if (!previousState.done && nextState.done) requestAnimationFrame(() => launchProjectCompletionCelebration(progress));
      }} catch (error) {{
        return;
      }}
    }}
    function replaceProjectProgress(html) {{
      const progress = document.getElementById('project-progress-pill');
      if (!progress || html === undefined || progress.outerHTML === html) return;
      const previousState = progressState(progress);
      const replacement = progressFromHtml(html);
      if (!replacement) return;
      const nextState = progressState(replacement);
      progress.replaceWith(replacement);
      if (!previousState.done && nextState.done) launchProjectCompletionCelebration(replacement);
    }}
    function updateProjectStatus(data, forceStoryboard = false) {{
      updateQueueEstimate(data.queue_estimate_seconds, data.queue_count);
      updateBrowserTitle(data.queue_count);
      replaceProjectProgress(data.progress_html);
      const actions = document.querySelector('.project-topbar .actions');
      if (actions && data.actions_html !== undefined && actions.innerHTML !== data.actions_html) actions.innerHTML = data.actions_html;
      Object.entries(data.rows || {{}}).forEach(([rowId, html]) => {{
        const row = document.getElementById(rowId);
        if (row) replaceProjectRow(row, html);
      }});
      if (data.storyboard_html !== undefined) replaceProjectStoryboard(data.storyboard_html, forceStoryboard);
      const finalizeData = document.getElementById('finalize-review-data');
      if (finalizeData && data.finalize_items_html !== undefined && !finalizeModalIsOpen()) finalizeData.innerHTML = data.finalize_items_html;
    }}
    async function refreshProjectStatus(projectId, forceStoryboard = false) {{
      if (!projectId) return;
      const response = await fetch('/projects/' + projectId + '/status');
      if (!response.ok) return;
      const data = await response.json();
      updateProjectStatus(data, forceStoryboard);
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
    async function submitQueueForm(event, form) {{
      if (event && event.preventDefault) event.preventDefault();
      if (!form) return false;
      const button = event && event.submitter ? event.submitter : form.querySelector('button');
      if (button) button.disabled = true;
      try {{
        const response = await fetch(form.action, {{
          method: form.method || 'post',
          body: new FormData(form),
        }});
        if (response.ok) await refreshJobsStatus();
      }} finally {{
        if (button) button.disabled = false;
      }}
      return false;
    }}
    async function submitProjectSidepanelForm(event, form) {{
      if (event && event.preventDefault) event.preventDefault();
      if (!form) return false;
      rememberScrollPosition();
      const submitter = event && event.submitter ? event.submitter : null;
      const button = submitter || form.querySelector('button');
      if (button) button.disabled = true;
      try {{
        const action = submitter && submitter.hasAttribute('formaction') ? submitter.formAction : form.action;
        const method = submitter && submitter.hasAttribute('formmethod') ? submitter.formMethod : form.method;
        const response = await fetch(action, {{
          method: method || 'post',
          body: new FormData(form),
        }});
        if (response.ok) {{
          const projectId = currentProjectId();
          if (projectId) await refreshProjectStatus(projectId, true);
        }}
      }} finally {{
        if (button) button.disabled = false;
      }}
      return false;
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
    function openGlobalSettingsModal() {{
      const box = document.getElementById('global-settings-modal');
      if (!box) return;
      box.classList.add('open');
    }}
    function closeGlobalSettingsModal() {{
      const box = document.getElementById('global-settings-modal');
      if (!box) return;
      box.classList.remove('open');
    }}
    function normalizeSearchText(value) {{
      return String(value || '').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');
    }}
    const projectBrowserPreferencesKey = 'vocavid.projectBrowserPreferences';
    function restoreProjectBrowserPreferences() {{
      const filter = document.getElementById('project-filter');
      const sort = document.getElementById('project-sort');
      if (!filter || !sort) return;
      try {{
        const preferences = JSON.parse(localStorage.getItem(projectBrowserPreferencesKey) || '{{}}');
        if (preferences.filter && Array.from(filter.options).some((option) => option.value === preferences.filter)) filter.value = preferences.filter;
        if (preferences.sort && Array.from(sort.options).some((option) => option.value === preferences.sort)) sort.value = preferences.sort;
      }} catch (error) {{
        // Keep the built-in defaults when browser storage is unavailable or invalid.
      }}
    }}
    function saveProjectBrowserPreferences() {{
      try {{
        localStorage.setItem(projectBrowserPreferencesKey, JSON.stringify({{
          filter: document.getElementById('project-filter')?.value || 'all',
          sort: document.getElementById('project-sort')?.value || 'newest',
        }}));
      }} catch (error) {{
        // Filtering and sorting remain usable when browser storage is unavailable.
      }}
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
      ['project-filter', 'project-sort'].forEach((id) => {{
        document.getElementById(id)?.addEventListener('change', saveProjectBrowserPreferences);
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
      restoreProjectBrowserPreferences();
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
    function openManualTimingModal() {{
      const box = document.getElementById('manual-timing-modal');
      if (!box) return;
      box.classList.add('open');
    }}
    function closeManualTimingModal() {{
      const box = document.getElementById('manual-timing-modal');
      if (!box) return;
      box.classList.remove('open');
    }}
    function openReelsModal() {{
      const box = document.getElementById('reels-modal');
      if (!box) return;
      box.classList.add('open');
      const projectId = currentProjectId();
      if (projectId) refreshReelsStatus(projectId);
    }}
    function closeReelsModal() {{
      const box = document.getElementById('reels-modal');
      if (!box) return;
      box.classList.remove('open');
    }}
    function hasActiveReelsVideo() {{
      return Array.from(document.querySelectorAll('#reels-modal video')).some((video) => {{
        return !video.paused || (video.currentTime && !video.ended);
      }});
    }}
    function preserveReelsVideos(replacement) {{
      const currentVideos = new Map();
      document.querySelectorAll('#reels-status video[src]').forEach((video) => {{
        currentVideos.set(video.getAttribute('src'), video);
      }});
      replacement.querySelectorAll('video[src]').forEach((video) => {{
        const current = currentVideos.get(video.getAttribute('src'));
        if (current) video.replaceWith(current);
      }});
    }}
    function preserveReelsUploadInput(replacement) {{
      const currentInput = document.querySelector('#reels-status input[name="source_video"]');
      if (!currentInput || !currentInput.files || !currentInput.files.length) return;
      const nextInput = replacement.querySelector('input[name="source_video"]');
      if (!nextInput) return;
      nextInput.replaceWith(currentInput);
    }}
    function pauseReelsUploadRefresh(milliseconds = 60000) {{
      reelsUploadInteractionUntil = Date.now() + milliseconds;
    }}
    function hasActiveReelsUploadInteraction() {{
      return Date.now() < reelsUploadInteractionUntil;
    }}
    function updateReelsStatus(data, force = false) {{
      const box = document.getElementById('reels-status');
      if (!box || data.reels_html === undefined) return;
      if (box.innerHTML === data.reels_html) return;
      if (!force && hasActiveReelsUploadInteraction()) return;
      if (!force && hasPendingReelsUpload()) return;
      if (!force && hasActiveReelsVideo()) return;
      const template = document.createElement('template');
      template.innerHTML = data.reels_html.trim();
      preserveReelsVideos(template.content);
      preserveReelsUploadInput(template.content);
      box.replaceChildren(template.content);
    }}
    function hasPendingReelsUpload() {{
      const input = document.querySelector('#reels-modal input[name="source_video"]');
      return !!(input && input.files && input.files.length);
    }}
    function updateReelsUploadLabel(input) {{
      pauseReelsUploadRefresh();
      const form = input ? input.closest('.reels-source-form') : null;
      const label = form ? form.querySelector('.reels-upload-name') : null;
      if (!label) return;
      const file = input && input.files && input.files.length ? input.files[0] : null;
      label.textContent = file ? 'Selected: ' + file.name : 'No upload selected';
    }}
    function markReelsFormProcessing(form, button) {{
      const card = form.closest('.reels-candidate-card');
      if (card) {{
        card.classList.add('reels-candidate-processing');
        const pill = card.querySelector('.reels-status-pill');
        if (pill) {{
          pill.textContent = 'queued';
          pill.className = 'reels-status-pill reels-status-queued';
        }}
      }}
      if (button) {{
        button.dataset.originalText = button.textContent;
        button.textContent = 'Processing...';
      }}
    }}
    async function refreshReelsStatus(projectId, force = false) {{
      if (!projectId) return;
      if (!force && hasActiveReelsUploadInteraction()) return;
      if (!force && hasPendingReelsUpload()) return;
      const response = await fetch('/projects/' + projectId + '/reels/status');
      if (!response.ok) return;
      if (!force && hasActiveReelsUploadInteraction()) return;
      if (!force && hasPendingReelsUpload()) return;
      updateReelsStatus(await response.json(), force);
    }}
    async function submitReelsForm(event) {{
      const form = event.target.closest('form[data-reels-form="1"]');
      if (!form) return;
      event.preventDefault();
      rememberScrollPosition();
      const button = event.submitter || form.querySelector('button');
      if (button) button.disabled = true;
      markReelsFormProcessing(form, button);
      try {{
        await fetch(form.action, {{
          method: form.method || 'post',
          body: new FormData(form),
        }});
        const projectId = currentProjectId();
        if (projectId) await refreshReelsStatus(projectId, true);
      }} finally {{
        if (button) {{
          button.disabled = false;
          if (button.dataset.originalText) button.textContent = button.dataset.originalText;
        }}
      }}
    }}
    async function pollReelsStatus(projectId) {{
      try {{
        const box = document.getElementById('reels-modal');
        if (box && box.classList.contains('open')) await refreshReelsStatus(projectId);
      }} catch (error) {{
        return;
      }} finally {{
        window.setTimeout(() => pollReelsStatus(projectId), 3500);
      }}
    }}
    function formatManualTimingTimestamp(seconds) {{
      const value = Math.max(0, Number(seconds) || 0);
      return value.toFixed(1);
    }}
    function updateManualTimingTimestamp(audio) {{
      const output = document.getElementById('manual-timing-current');
      if (!output) return;
      output.textContent = formatManualTimingTimestamp(audio.currentTime);
    }}
    function manualTimingValueIsOpen(input) {{
      const value = String(input.value || '').trim().replace(',', '.');
      if (!value) return true;
      return Number(value) === 0;
    }}
    function setManualTimingInput(input, timestamp) {{
      input.value = timestamp;
      input.dispatchEvent(new Event('input', {{ bubbles: true }}));
      input.classList.add('manual-time-filled');
      window.setTimeout(() => input.classList.remove('manual-time-filled'), 450);
    }}
    function applyManualTimingTimestamp() {{
      const audio = document.getElementById('manual-timing-audio');
      const table = document.querySelector('.manual-timing-table');
      if (!audio || !table) return;
      const timestamp = formatManualTimingTimestamp(audio.currentTime);
      const rows = Array.from(table.querySelectorAll('tbody tr')).filter((row) => row.querySelector('input[name="start_secs"]'));
      for (let index = 1; index < rows.length; index += 1) {{
        const previousEnd = rows[index - 1].querySelector('input[name="end_secs"]');
        const currentStart = rows[index].querySelector('input[name="start_secs"]');
        if (previousEnd && currentStart && manualTimingValueIsOpen(previousEnd) && manualTimingValueIsOpen(currentStart)) {{
          setManualTimingInput(previousEnd, timestamp);
          setManualTimingInput(currentStart, timestamp);
          return;
        }}
      }}
      const openEnd = rows.map((row) => row.querySelector('input[name="end_secs"]')).find((input) => input && manualTimingValueIsOpen(input));
      if (openEnd) setManualTimingInput(openEnd, timestamp);
    }}
    function addManualInterlude(button, afterLineIndex) {{
      const insertRow = button.closest('tr');
      if (!insertRow) return;
      const row = document.createElement('tr');
      row.className = 'manual-interlude-row';
      row.innerHTML = `
        <td class="manual-boundary-cell"><button class="manual-interlude-remove" type="button" title="Interlude entfernen" onclick="this.closest('tr').remove()">&times;</button></td>
        <td>
          <input type="hidden" name="line_indices" value="">
          <input type="hidden" name="row_types" value="interlude">
          <input type="hidden" name="interlude_after_line_indices" value="${{afterLineIndex}}">
          <textarea class="manual-lyric-text" name="clean_texts" required>[Instrumental]</textarea>
        </td>
        <td><select name="sections">
          <option value="Intro">Intro</option>
          <option value="Verse">Verse</option>
          <option value="Pre-Chorus">Pre-Chorus</option>
          <option value="Chorus">Chorus</option>
          <option value="Refrain">Refrain</option>
          <option value="Bridge">Bridge</option>
          <option value="Instrumental" selected>Instrumental</option>
          <option value="Interlude">Interlude</option>
          <option value="Instrumental Fade-Out">Instrumental Fade-Out</option>
          <option value="Outro">Outro</option>
        </select></td>
        <td><input class="manual-time-input" name="start_secs" placeholder="0.0" required></td>
        <td><input class="manual-time-input" name="end_secs" placeholder="0.0" required></td>`;
      insertRow.before(row);
      row.querySelector('textarea').focus();
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
    function selectStoryboardCard(storyboard, card, focusCard = false) {{
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
      if (focusCard) {{
        card.focus({{ preventScroll: true }});
        card.scrollIntoView({{ block: 'nearest', inline: 'nearest', behavior: 'smooth' }});
      }}
    }}
    function selectStoryboardTemplate(templateId) {{
      const storyboard = document.getElementById('project-storyboard');
      if (!storyboard || !templateId) return;
      const card = storyboard.querySelector('[data-inspector-template="' + templateId + '"]');
      if (!card) return;
      selectStoryboardCard(storyboard, card, true);
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
      return 'VocaVid-scroll:' + window.location.pathname;
    }}
    function storyboardSelectionStorageKey() {{
      return 'VocaVid-storyboard-selection:' + window.location.pathname;
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
        sessionStorage.setItem('VocaVid-storyboard-selection:' + href, templateId);
      }}
      window.location.href = href;
    }}
    function confirmProjectSettingsSave(form) {{
      rememberScrollPosition();
      return true;
    }}
    document.addEventListener('submit', submitReelsForm);
    document.addEventListener('submit', (event) => {{
      const form = event.target.closest('form[data-queue-form="1"]');
      if (form) submitQueueForm(event, form);
    }});
    document.addEventListener('submit', (event) => {{
      const form = event.target.closest('form[data-project-sidepanel-form="1"]');
      if (form) submitProjectSidepanelForm(event, form);
    }});
    document.addEventListener('submit', rememberScrollPosition);
    document.addEventListener('keydown', handleFinalizeKeyboard);
    document.addEventListener('pointerdown', (event) => {{
      if (event.target.closest('#reels-modal input[name="source_video"]')) pauseReelsUploadRefresh();
    }});
    document.addEventListener('focusin', (event) => {{
      if (event.target.closest('#reels-modal input[name="source_video"]')) pauseReelsUploadRefresh();
    }});
    document.addEventListener('pointerdown', (event) => {{
      const handle = event.target.closest('.segment-inspector-resize-handle');
      if (handle) beginSegmentInspectorResize(event, handle);
    }});
    document.addEventListener('keydown', (event) => {{
      const handle = event.target.closest('.segment-inspector-resize-handle');
      if (!handle || (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight')) return;
      const workspace = handle.closest('.storyboard-workspace');
      if (!workspace) return;
      event.preventDefault();
      const inspector = workspace.querySelector('.segment-inspector');
      const currentWidth = inspector ? inspector.getBoundingClientRect().width : 520;
      setSegmentInspectorWidth(currentWidth + (event.key === 'ArrowLeft' ? 24 : -24), true);
    }});
    document.addEventListener('DOMContentLoaded', () => {{
      rememberProjectRows();
      rememberProjectStoryboard();
      setupProjectBrowserControls();
      restoreSegmentInspectorWidth();
      launchStoredProjectCompletionCelebration();
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
    function finalizeModalIsOpen() {{
      const box = document.getElementById('finalize-modal');
      return !!(box && box.classList.contains('open'));
    }}
    function currentFinalizeItem() {{
      return finalizeItems[finalizeItemCursor] || null;
    }}
    function stopFinalizeCountdown() {{
      if (finalizeCountdownTimer !== null) window.clearInterval(finalizeCountdownTimer);
      finalizeCountdownTimer = null;
      const countdown = document.getElementById('finalize-countdown');
      if (countdown) countdown.hidden = true;
    }}
    function setFinalizeActionsVisible(visible) {{
      const actions = document.getElementById('finalize-actions');
      if (actions) actions.hidden = !visible;
    }}
    function setFinalizeInstruction(message, state = '') {{
      const instruction = document.getElementById('finalize-instruction');
      if (!instruction) return;
      instruction.textContent = message;
      instruction.dataset.state = state;
    }}
    function openFinalizeModal() {{
      const box = document.getElementById('finalize-modal');
      const data = document.getElementById('finalize-review-data');
      if (!box || !data) return;
      finalizeItems = Array.from(data.querySelectorAll('.finalize-review-item')).filter((item) => item.dataset.approved !== '1');
      finalizeItemCursor = 0;
      box.classList.add('open');
      if (!finalizeItems.length) {{
        finishFinalizeReview();
        return;
      }}
      loadFinalizeItem();
    }}
    function closeFinalizeModal() {{
      stopFinalizeCountdown();
      const box = document.getElementById('finalize-modal');
      const video = document.getElementById('finalize-video');
      if (video) {{
        video.pause();
        video.onended = null;
        video.removeAttribute('src');
        video.load();
      }}
      closeFinalizePromptEditor();
      setFinalizeActionsVisible(false);
      if (box) box.classList.remove('open');
      finalizeMode = 'closed';
      const projectId = currentProjectId();
      if (projectId) refreshProjectStatus(projectId);
    }}
    function loadFinalizeItem() {{
      stopFinalizeCountdown();
      closeFinalizePromptEditor();
      setFinalizeActionsVisible(false);
      const item = currentFinalizeItem();
      if (!item) {{
        finishFinalizeReview();
        return;
      }}
      const video = document.getElementById('finalize-video');
      const position = document.getElementById('finalize-position');
      const title = document.getElementById('finalize-title');
      if (!video || !position || !title) return;
      position.textContent = '#' + item.dataset.position + ' / ' + item.dataset.total;
      title.textContent = item.dataset.title || 'Untitled segment';
      setFinalizeInstruction('No action needed: this clip will be marked as finished after playback. Press Space or Enter if it needs work.');
      finalizeMode = 'playing';
      video.onended = startFinalizeCountdown;
      video.src = item.dataset.src;
      video.currentTime = 0;
      const playPromise = video.play();
      if (playPromise && playPromise.catch) {{
        playPromise.catch(() => setFinalizeInstruction('Press Play to start the review. Space or Enter opens the actions.'));
      }}
    }}
    function startFinalizeCountdown() {{
      if (!finalizeModalIsOpen() || !currentFinalizeItem()) return;
      stopFinalizeCountdown();
      finalizeMode = 'countdown';
      finalizeCountdownValue = 3;
      const countdown = document.getElementById('finalize-countdown');
      if (countdown) {{
        countdown.hidden = false;
        countdown.textContent = String(finalizeCountdownValue);
      }}
      setFinalizeInstruction('Clip finished. Marking it as finished automatically...');
      finalizeCountdownTimer = window.setInterval(() => {{
        finalizeCountdownValue -= 1;
        if (finalizeCountdownValue <= 0) {{
          stopFinalizeCountdown();
          approveCurrentFinalizeItem();
          return;
        }}
        if (countdown) countdown.textContent = String(finalizeCountdownValue);
      }}, 1000);
    }}
    function pauseFinalizeForActions() {{
      if (!finalizeModalIsOpen() || !currentFinalizeItem()) return;
      stopFinalizeCountdown();
      const video = document.getElementById('finalize-video');
      if (video) video.pause();
      finalizeMode = 'actions';
      setFinalizeActionsVisible(true);
      setFinalizeInstruction('Choose an action or press 1–5. The review continues after generation is queued.');
    }}
    async function approveCurrentFinalizeItem() {{
      const item = currentFinalizeItem();
      if (!item || finalizeMode === 'saving') return;
      finalizeMode = 'saving';
      setFinalizeInstruction('Marking clip as finished...');
      const formData = new FormData();
      formData.append('video_approved', '1');
      try {{
        const response = await fetch('/projects/' + currentProjectId() + '/' + item.dataset.itemKind + '/' + item.dataset.itemIndex + '/approval', {{ method: 'post', body: formData }});
        if (!response.ok) throw new Error('Approval failed');
        item.dataset.approved = '1';
        await advanceFinalizeReview();
      }} catch (error) {{
        finalizeMode = 'actions';
        setFinalizeActionsVisible(true);
        setFinalizeInstruction('Could not mark this clip as finished. Choose an action or try again.', 'error');
      }}
    }}
    async function advanceFinalizeReview() {{
      finalizeItemCursor += 1;
      const projectId = currentProjectId();
      if (projectId) refreshProjectStatus(projectId);
      loadFinalizeItem();
    }}
    function finishFinalizeReview() {{
      stopFinalizeCountdown();
      closeFinalizePromptEditor();
      setFinalizeActionsVisible(false);
      const video = document.getElementById('finalize-video');
      const position = document.getElementById('finalize-position');
      const title = document.getElementById('finalize-title');
      if (video) {{
        video.pause();
        video.onended = null;
        video.removeAttribute('src');
        video.load();
      }}
      const needsAnotherPass = finalizeItems.some((item) => item.dataset.approved !== '1');
      if (position) position.textContent = 'Finalize complete';
      if (title) title.textContent = needsAnotherPass ? 'Review pass complete' : 'All clips are finished';
      setFinalizeInstruction(
        needsAnotherPass ? 'Queued changes will need another review pass.' : 'Your project is ready for Assemble & Render MP4.',
        'success'
      );
      finalizeMode = 'complete';
      const projectId = currentProjectId();
      if (projectId) refreshProjectStatus(projectId);
    }}
    async function queueFinalizeAction(action) {{
      const item = currentFinalizeItem();
      if (!item || finalizeMode === 'queueing') return;
      finalizeMode = 'queueing';
      document.querySelectorAll('#finalize-actions button').forEach((button) => button.disabled = true);
      setFinalizeInstruction('Adding job to the queue...');
      const formData = new FormData();
      formData.append('selected_lines', item.dataset.itemIndex);
      try {{
        const response = await fetch('/projects/' + currentProjectId() + '/' + action, {{ method: 'post', body: formData }});
        if (!response.ok) throw new Error('Queue request failed');
        await advanceFinalizeReview();
      }} catch (error) {{
        finalizeMode = 'actions';
        setFinalizeInstruction('Could not add the job to the queue. Please try again.', 'error');
      }} finally {{
        document.querySelectorAll('#finalize-actions button').forEach((button) => button.disabled = false);
      }}
    }}
    function openFinalizePromptEditor(kind) {{
      const item = currentFinalizeItem();
      const editor = document.getElementById('finalize-prompt-editor');
      const label = document.getElementById('finalize-prompt-label');
      const textarea = document.getElementById('finalize-prompt-textarea');
      if (!item || !editor || !label || !textarea) return;
      stopFinalizeCountdown();
      const isVideo = kind === 'video';
      editor.dataset.promptKind = isVideo ? 'video' : 'image';
      label.textContent = isVideo ? 'Edit Video Prompt' : 'Edit Image Prompt';
      textarea.name = isVideo ? 'video_prompt' : 'prompt';
      textarea.value = isVideo ? (item.dataset.videoPrompt || '') : (item.dataset.imagePrompt || '');
      editor.hidden = false;
      setFinalizeActionsVisible(false);
      finalizeMode = 'prompt';
      textarea.focus();
    }}
    function closeFinalizePromptEditor() {{
      const editor = document.getElementById('finalize-prompt-editor');
      if (!editor || editor.hidden) return;
      editor.hidden = true;
      if (finalizeModalIsOpen() && currentFinalizeItem()) {{
        finalizeMode = 'actions';
        setFinalizeActionsVisible(true);
        setFinalizeInstruction('Choose an action or press 1–5.');
      }}
    }}
    async function submitFinalizePrompt(event, form) {{
      if (event && event.preventDefault) event.preventDefault();
      const item = currentFinalizeItem();
      const textarea = document.getElementById('finalize-prompt-textarea');
      if (!item || !textarea) return false;
      const kind = form.dataset.promptKind === 'video' ? 'video' : 'image';
      const submitter = event && event.submitter ? event.submitter : null;
      const suffix = submitter && submitter.dataset.aiFill === '1' ? '/ai-fill' : '/save';
      const url = '/projects/' + currentProjectId() + '/' + item.dataset.itemKind + '/' + item.dataset.itemIndex + '/prompts/' + kind + suffix;
      const formData = new FormData();
      formData.append(kind === 'video' ? 'video_prompt' : 'prompt', textarea.value);
      if (submitter) submitter.disabled = true;
      try {{
        const response = await fetch(url, {{ method: 'post', body: formData }});
        if (!response.ok) throw new Error('Prompt save failed');
        if (kind === 'video') item.dataset.videoPrompt = textarea.value;
        else item.dataset.imagePrompt = textarea.value;
        closeFinalizePromptEditor();
        setFinalizeInstruction(suffix === '/ai-fill' ? 'AI fill added to the queue. Choose the next action.' : 'Prompt saved. Choose the next action.', 'success');
      }} catch (error) {{
        setFinalizeInstruction('Could not save the prompt. Please try again.', 'error');
      }} finally {{
        if (submitter) submitter.disabled = false;
      }}
      return false;
    }}
    function handleFinalizeKeyboard(event) {{
      if (!finalizeModalIsOpen()) return;
      const target = event.target;
      const editing = target && target.closest && target.closest('input, textarea, select');
      if (event.key === 'Escape') {{
        if (finalizeMode === 'prompt') closeFinalizePromptEditor();
        else closeFinalizeModal();
        return;
      }}
      if (editing || finalizeMode === 'prompt' || finalizeMode === 'queueing' || finalizeMode === 'saving') return;
      if ((event.key === ' ' || event.key === 'Enter') && (finalizeMode === 'playing' || finalizeMode === 'countdown')) {{
        event.preventDefault();
        pauseFinalizeForActions();
        return;
      }}
      if (finalizeMode !== 'actions') return;
      const shortcuts = {{ '1': 'clips', '2': 'avatar-image', '3': 'images' }};
      if (shortcuts[event.key]) {{
        event.preventDefault();
        queueFinalizeAction(shortcuts[event.key]);
      }} else if (event.key === '4') {{
        event.preventDefault();
        openFinalizePromptEditor('image');
      }} else if (event.key === '5') {{
        event.preventDefault();
        openFinalizePromptEditor('video');
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
