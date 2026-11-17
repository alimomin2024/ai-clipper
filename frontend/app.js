document.addEventListener('DOMContentLoaded', () => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const qa = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const sensitiveKeys = new Set(['AI_CLIPPER_ADMIN_KEY']);
  const fallbackPresets = {
    subtitle_presets: {
      hormozi: { name: 'Signal yellow' },
      neon_green: { name: 'Neon green' },
      cyber_cyan: { name: 'Electric cyan' },
      clean_minimal: { name: 'Quiet minimal' }
    },
    layout_modes: [
      { id: 'smart_crop', name: 'AI face tracking', description: 'Keep the speaker centered' },
      { id: 'blurred_background', name: 'Blurred background', description: 'Preserve the full frame' },
      { id: 'split_screen', name: 'Split screen', description: 'Stack two speakers' }
    ],
    aspect_ratios: [
      { id: '9:16', name: '9:16 vertical', width: 1080, height: 1920 },
      { id: '1:1', name: '1:1 square', width: 1080, height: 1080 },
      { id: '16:9', name: '16:9 landscape', width: 1920, height: 1080 }
    ],
    upload_max_mb: 500,
    max_target_clips: 6
  };

  function storageFor(key) {
    return sensitiveKeys.has(key) ? window.sessionStorage : window.localStorage;
  }
  function readStorage(key) {
    try { return storageFor(key).getItem(key) || ''; } catch (_) { return ''; }
  }
  function writeStorage(key, value) {
    try {
      const storage = storageFor(key);
      if (value) storage.setItem(key, value); else storage.removeItem(key);
    } catch (_) { /* Storage may be unavailable in private browsing. */ }
  }

  const state = {
    route: { name: 'dashboard' },
    projects: [],
    projectsLoaded: false,
    projectsLoading: false,
    projectsError: '',
    projectsRequestId: 0,
    selectedProject: null,
    selectedClip: null,
    currentPlatform: 'tiktok',
      schedule: { items: [], projectId: null, loading: false },
    presets: fallbackPresets,
    presetsLoading: false,
    presetsError: '',
    uploadLimitMb: 1024,
    create: {
      sourceMode: 'url',
      url: '',
      file: null,
      channel: 'shorts',
      submitting: false,
      options: { subtitle_preset: 'hormozi', layout_mode: 'smart_crop', aspect_ratio: '9:16', target_clips: 4 }
    },
    job: {
      id: readStorage('AI_CLIPPER_ACTIVE_JOB'),
      snapshot: null,
      eventSource: null,
      reconnectTimer: null,
      pollingTimer: null,
      reconnectAttempts: 0,
      pollingFailures: 0,
      pollingErrorNotified: false,
      settled: false,
      lastSubmission: null,
      activity: []
    },
    admin: {
      loading: false,
      unauthorized: false,
      lastSync: null,
      live: true,
      refreshTimer: null,
      inFlight: new Map(),
      jobs: [],
      clips: [],
      logs: []
    },
    confirmResolver: null,
    lastDialogFocus: null,
    healthRetryTimer: null
  };

  const refs = {
    appShell: $('appShell'),
    rail: $('workspaceRail'),
    railClose: $('railClose'),
    railScrim: $('railScrim'),
    mobileRailToggle: $('mobileRailToggle'),
    commandButton: $('commandButton'),
    routeSection: $('routeSection'),
    routeTitle: $('routeTitle'),
    topEnginePill: $('topEnginePill'),
    topEngineText: $('topEngineText'),
    railStatusOrb: $('railStatusOrb'),
    railStatusText: $('railStatusText'),
    railStatusDetail: $('railStatusDetail'),
    railProjectCount: $('railProjectCount'),
    dashboardProjectCount: $('dashboardProjectCount'),
    dashboardClipCount: $('dashboardClipCount'),
    dashboardAttention: $('dashboardAttention'),
    dashboardDate: $('dashboardDate'),
    dashboardEngine: $('dashboardEngine'),
    dashboardEngineDetail: $('dashboardEngineDetail'),
    dashboardRun: $('dashboardRun'),
    dashboardNextCopy: $('dashboardNextCopy'),
    dashboardNextAction: $('dashboardNextAction'),
    dashboardProjectList: $('dashboardProjectList'),
    createUrlForm: $('createUrlForm'),
    createUrlInput: $('createUrlInput'),
    createUploadEntry: $('createUploadEntry'),
    createFileInput: $('createFileInput'),
    createDropzone: $('createDropzone'),
    createDropzoneTitle: $('createDropzoneTitle'),
    createUploadMeta: $('createUploadMeta'),
    createUploadLimit: $('createUploadLimit'),
    sourceContinue: $('sourceContinue'),
    uploadContinue: $('uploadContinue'),
    createCaptionSelect: $('createCaptionSelect'),
    createLayoutSelect: $('createLayoutSelect'),
    createAspectSelect: $('createAspectSelect'),
    createClipCountSelect: $('createClipCountSelect'),
    directionEngineNote: $('directionEngineNote'),
    createReviewSummary: $('createReviewSummary'),
    createNotice: $('createNotice'),
    startCreate: $('startCreate'),
    createContextArt: $('createContextArt'),
    createContextTitle: $('createContextTitle'),
    createContextMeta: $('createContextMeta'),
    createContextList: $('createContextList'),
    createContextOutput: $('createContextOutput'),
    createSaveState: $('createSaveState'),
    createPresetStatus: $('createPresetStatus'),
    jobIdLabel: $('jobIdLabel'),
    jobTitle: $('jobTitle'),
    jobSubtitle: $('jobSubtitle'),
    jobStatusPill: $('jobStatusPill'),
    jobMessage: $('jobMessage'),
    jobProgressPercent: $('jobProgressPercent'),
    jobProgressBar: $('jobProgressBar'),
    jobStages: $('jobStages'),
    jobActivity: $('jobActivity'),
    jobConnectionState: $('jobConnectionState'),
    jobFooterNote: $('jobFooterNote'),
    jobDetailId: $('jobDetailId'),
    jobDetailSource: $('jobDetailSource'),
    jobDetailOutput: $('jobDetailOutput'),
    jobDetailMode: $('jobDetailMode'),
    jobRetry: $('jobRetry'),
    jobOpenProject: $('jobOpenProject'),
    projectTitle: $('projectTitle'),
    projectSubtitle: $('projectSubtitle'),
    projectStatusDot: $('projectStatusDot'),
    projectDelete: $('projectDelete'),
    projectDownloadAll: $('projectDownloadAll'),
    projectClipCount: $('projectClipCount'),
    projectClipRail: $('projectClipRail'),
    projectPlayerLabel: $('projectPlayerLabel'),
    projectPlayerFormat: $('projectPlayerFormat'),
    projectVideo: $('projectVideo'),
    projectVideoEmpty: $('projectVideoEmpty'),
    projectDownloadMain: $('projectDownloadMain'),
    projectCopyButton: $('projectCopyButton'),
    projectTimeReadout: $('projectTimeReadout'),
    projectTrimStart: $('projectTrimStart'),
    projectTrimEnd: $('projectTrimEnd'),
    projectClipTitle: $('projectClipTitle'),
    projectScore: $('projectScore'),
    projectHook: $('projectHook'),
    projectReason: $('projectReason'),
    projectQuote: $('projectQuote'),
    projectCaptionSelect: $('projectCaptionSelect'),
    projectLayoutSelect: $('projectLayoutSelect'),
    projectAspectSelect: $('projectAspectSelect'),
    projectSaveRender: $('projectSaveRender'),
    projectOpenWords: $('projectOpenWords'),
    projectPublishText: $('projectPublishText'),
    projectCopyText: $('projectCopyText'),
    librarySearch: $('librarySearch'),
    libraryFilter: $('libraryFilter'),
    libraryRefresh: $('libraryRefresh'),
    librarySummaryText: $('librarySummaryText'),
    libraryList: $('libraryList'),
    opsSyncStatus: $('opsSyncStatus'),
    opsLiveRefresh: $('opsLiveRefresh'),
    opsRefresh: $('opsRefresh'),
    opsAccessState: $('opsAccessState'),
    opsAccessMessage: $('opsAccessMessage'),
    opsEngineStatus: $('opsEngineStatus'),
    opsEngineDetail: $('opsEngineDetail'),
    opsEngineMeta: $('opsEngineMeta'),
    opsActiveJobs: $('opsActiveJobs'),
    opsWorkerMeta: $('opsWorkerMeta'),
    opsStorage: $('opsStorage'),
    opsStorageDetail: $('opsStorageDetail'),
    opsDiskMeta: $('opsDiskMeta'),
    opsInventory: $('opsInventory'),
    opsInventoryDetail: $('opsInventoryDetail'),
    opsInventoryMeta: $('opsInventoryMeta'),
    opsJobSearch: $('opsJobSearch'),
    opsJobStatus: $('opsJobStatus'),
    opsClipSearch: $('opsClipSearch'),
    opsJobsTable: $('opsJobsTable'),
    opsClipsTable: $('opsClipsTable'),
    opsPurge: $('opsPurge'),
    opsVacuum: $('opsVacuum'),
    opsClearJobs: $('opsClearJobs'),
    scheduleTime: $('scheduleTime'),
    schedulePlatforms: $('schedulePlatforms'),
    scheduleClip: $('scheduleClip'),
    scheduleNotice: $('scheduleNotice'),
    scheduledPostList: $('scheduledPostList'),
    opsLogLevel: $('opsLogLevel'),
    opsRefreshLogs: $('opsRefreshLogs'),
    opsLogConsole: $('opsLogConsole'),
    settingsDialog: $('settingsDialog'),
    openSettings: $('openSettings'),
    topSettings: $('topSettings'),
    opsOpenSettings: $('opsOpenSettings'),
    closeSettings: $('closeSettings'),
    cancelSettings: $('cancelSettings'),
    saveSettings: $('saveSettings'),
    settingsAdmin: $('settingsAdmin'),
    confirmDialog: $('confirmDialog'),
    confirmTitle: $('confirmTitle'),
    confirmMessage: $('confirmMessage'),
    closeConfirm: $('closeConfirm'),
    cancelConfirm: $('cancelConfirm'),
    acceptConfirm: $('acceptConfirm'),
    wordsDialog: $('wordsDialog'),
    closeWords: $('closeWords'),
    cancelWords: $('cancelWords'),
    saveWords: $('saveWords'),
    wordsList: $('wordsList'),
    toastStack: $('toastStack')
  };

  const screenTitles = {
    dashboard: ['HOME', 'Content desk'],
    create: ['CREATE', 'Production brief'],
    job: ['RUN ROOM', 'Production room'],
    project: ['PROJECT', 'Project workspace'],
    library: ['LIBRARY', 'Content inventory'],
    ops: ['OPERATIONS', 'Privileged console']
  };

  function escapeHtml(value) {
    return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }
  function escapeAttr(value) { return escapeHtml(value).replace(/`/g, '&#096;'); }
  function mediaUrl(value) {
    const candidate = String(value || '');
    return candidate.startsWith('/storage/') || /^https?:\/\//i.test(candidate) ? candidate : '';
  }
  function setText(element, value) { if (element) element.textContent = String(value ?? ''); }
  function formatDuration(seconds) {
    const total = Math.max(0, Math.round(Number(seconds) || 0));
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
  }
  function formatSeconds(seconds) { return `${(Number(seconds) || 0).toFixed(1)}s`; }
  function formatDate(value) {
    if (!value) return 'Recently created';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 'Recently created' : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }
  function normalizeStatus(value) { return String(value || '').toUpperCase(); }
  function clipId(clip) { return String(clip?.id || clip?.clip_id || ''); }
  function hasSource() {
    return state.create.sourceMode === 'upload' ? Boolean(state.create.file) : Boolean(String(state.create.url || '').trim());
  }
  const processingStatuses = new Set(['QUEUED', 'PROCESSING', 'DOWNLOADING', 'TRANSCRIBING', 'ANALYZING', 'CLIPPING']);
  function isProcessingStatus(status) { return processingStatuses.has(normalizeStatus(status)); }
  function isFailedStatus(status) { return ['FAILED', 'CANCELLED'].includes(normalizeStatus(status)); }
  function projectMatchesFilter(project, filter) {
    const status = projectStatus(project);
    if (filter === 'processing') return isProcessingStatus(status);
    if (filter === 'failed') return isFailedStatus(status);
    return filter === 'all' || status.toLowerCase() === filter;
  }
  function clipDownloadUrl(clip) {
    const id = clipId(clip);
    const ratio = String(clip?.aspect_ratio || '9:16').replace(':', 'x');
    return id ? `/api/clips/${encodeURIComponent(`${id}_${ratio}.mp4`)}/download` : mediaUrl(clip?.video_url) || '';
  }
  function normalizedProject(project) {
    if (!project) return null;
    const source = project.source_info || {};
    return { ...project, id: project.id || project.project_id, title: project.title || source.title || 'Untitled project', duration: project.duration || source.duration || 0, thumbnail_url: project.thumbnail_url || source.thumbnail || '', transcript: project.transcript || {}, clips: Array.isArray(project.clips) ? project.clips : [] };
  }

  class ApiError extends Error { constructor(message, status) { super(message); this.name = 'ApiError'; this.status = status; } }
  async function apiRequest(url, options = {}) {
    const headers = Object.assign({}, options.headers || {});
    const adminKey = readStorage('AI_CLIPPER_ADMIN_KEY');
    if (adminKey && String(url).includes('/api/admin')) headers['X-Admin-Key'] = adminKey;
    let response;
    try { response = await fetch(url, { ...options, headers }); } catch (error) { throw new ApiError(error.message || 'Network request failed.', 0); }
    const raw = await response.text();
    let data = {};
    if (raw) { try { data = JSON.parse(raw); } catch (_) { data = { raw }; } }
    if (!response.ok) throw new ApiError(data.detail || data.message || `Request failed (${response.status})`, response.status);
    return data;
  }
  function adminRequest(key, url, options = {}) {
    const existing = state.admin.inFlight.get(key);
    if (existing) return existing;
    const request = apiRequest(url, options).finally(() => state.admin.inFlight.delete(key));
    state.admin.inFlight.set(key, request);
    return request;
  }
  function showToast(message, type = 'success') {
    if (!refs.toastStack) return;
    const toast = document.createElement('div');
    toast.className = `toast${type === 'error' ? ' is-error' : ''}`;
    toast.textContent = message;
    refs.toastStack.appendChild(toast);
    window.setTimeout(() => toast.remove(), 3800);
  }
  function openDialog(dialog) {
    if (!dialog) return;
    state.lastDialogFocus = document.activeElement;
    if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', '');
    window.setTimeout(() => dialog.querySelector('button, input, select')?.focus(), 0);
  }
  function closeDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.close === 'function' && dialog.open) dialog.close(); else dialog.removeAttribute('open');
    if (state.lastDialogFocus?.focus) window.setTimeout(() => state.lastDialogFocus.focus(), 0);
    state.lastDialogFocus = null;
  }
  function bindBackdrop(dialog, onClose) {
    dialog?.addEventListener('click', (event) => { if (event.target === dialog) onClose(); });
  }

  function parseRoute() {
    const raw = window.location.hash.replace(/^#/, '').replace(/^\/+|\/+$/g, '').toLowerCase();
    if (!raw || raw === 'home') return { name: 'dashboard' };
    const parts = raw.split('/').filter(Boolean);
    if (['landing', 'marketing', 'solutions', 'pricing', 'plans'].includes(parts[0])) return { name: 'dashboard' };
    if (parts[0] === 'studio') return { name: 'create', step: 'source' };
    if (parts[0] === 'create') return { name: 'create', step: ['source', 'direction', 'review'].includes(parts[1]) ? parts[1] : 'source' };
    if (parts[0] === 'jobs' || parts[0] === 'job') return { name: 'job', id: parts[1] || state.job.id };
    if (parts[0] === 'projects' || parts[0] === 'project') return { name: 'project', id: parts[1] || '' };
    if (parts[0] === 'admin' || parts[0] === 'ops') return { name: 'ops' };
    if (parts[0] === 'library') return { name: 'library' };
    if (parts[0] === 'dashboard') return { name: 'dashboard' };
    return { name: 'dashboard' };
  }
  function routePath(route) {
    if (typeof route === 'string') return route.replace(/^#/, '');
    if (route.name === 'create') return `create/${route.step || 'source'}`;
    if (route.name === 'job') return `jobs/${encodeURIComponent(route.id || state.job.id || '')}`;
    if (route.name === 'project') return `projects/${encodeURIComponent(route.id || '')}`;
    return route.name;
  }
  function navigate(route, replace = false) {
    const path = routePath(typeof route === 'string' ? parseRouteFromString(route) : route);
    const hash = `#${path}`;
    if (window.location.hash !== hash) window.history[replace ? 'replaceState' : 'pushState']({}, '', hash);
    renderRoute(parseRoute());
  }
  function parseRouteFromString(value) {
    const path = String(value || '').replace(/^#/, '').replace(/^\/+|\/+$/g, '');
    const parts = path.split('/').filter(Boolean);
    if (parts[0] === 'create') return { name: 'create', step: parts[1] || 'source' };
    if (parts[0] === 'jobs' || parts[0] === 'job') return { name: 'job', id: parts[1] || state.job.id };
    if (parts[0] === 'projects' || parts[0] === 'project') return { name: 'project', id: parts[1] || '' };
    if (parts[0] === 'admin' || parts[0] === 'ops') return { name: 'ops' };
    if (['landing', 'marketing', 'solutions', 'pricing', 'plans'].includes(parts[0])) return { name: 'dashboard' };
    return { name: parts[0] || 'dashboard' };
  }
  function closeMobileRail() {
    refs.rail?.classList.remove('is-open');
    refs.railScrim?.classList.remove('is-visible');
    refs.mobileRailToggle?.setAttribute('aria-expanded', 'false');
  }
  function setActiveScreen(name) {
    qa('[data-screen]').forEach((screen) => screen.classList.toggle('is-active', screen.dataset.screen === name));
    qa('[data-route]').forEach((link) => {
      const target = parseRouteFromString(link.dataset.route || '').name;
      link.classList.toggle('is-active', target === name || (name === 'create' && target === 'create'));
    });
    closeMobileRail();
  }
  function updateRouteChrome(name) {
    const title = screenTitles[name] || screenTitles.dashboard;
    setText(refs.routeSection, title[0]);
    setText(refs.routeTitle, title[1]);
  }

  async function renderRoute(route) {
    try { await renderRouteInternal(route); }
    catch (error) {
      console.error('Route render failed', error);
      showToast(error.message || 'This workspace view could not be loaded.', 'error');
      if (state.route.name !== 'dashboard') {
        state.route = { name: 'dashboard' };
        setActiveScreen('dashboard');
        updateRouteChrome('dashboard');
        renderDashboard();
      }
    }
  }
  async function renderRouteInternal(route) {
    if (route.name === 'project' && !route.id) route = { name: 'library' };
    state.route = route;
    setActiveScreen(route.name);
    updateRouteChrome(route.name);
    if (route.name === 'dashboard') { renderDashboard(); await loadProjects(); renderDashboard(); }
    if (route.name === 'create') renderCreate();
    if (route.name === 'job') await hydrateJob(route.id);
    if (route.name === 'project') { renderProjectLoading(); await loadProject(route.id); }
    if (route.name === 'library') { renderLibrary(); await loadProjects(); renderLibrary(); }
    if (route.name === 'ops') { await loadOperations(); startAdminRefresh(); }
    else stopAdminRefresh();
  }

  function setEngineState(mode, label, detail) {
    const classes = ['is-offline', 'is-error'];
    refs.railStatusOrb?.classList.remove(...classes);
    refs.topEnginePill?.classList.remove(...classes);
    if (mode === 'offline') { refs.railStatusOrb?.classList.add('is-offline'); refs.topEnginePill?.classList.add('is-offline'); }
    if (mode === 'error') { refs.railStatusOrb?.classList.add('is-error'); refs.topEnginePill?.classList.add('is-error'); }
    setText(refs.railStatusText, label); setText(refs.topEngineText, label); setText(refs.railStatusDetail, detail);
    setText(refs.dashboardEngine, label); setText(refs.dashboardEngineDetail, detail);
  }
  async function checkHealth() {
    try {
      const data = await apiRequest('/api/health');
      if (state.healthRetryTimer) { window.clearTimeout(state.healthRetryTimer); state.healthRetryTimer = null; }
      const modelReady = Boolean(data.checks?.offline_whisper_model);
      if (modelReady) setEngineState('offline', 'Local mode', 'Offline Whisper · local ranking');
      else setEngineState('error', 'Model setup needed', 'Run prepare_offline.py once');
      return data;
    } catch (_) {
      setEngineState('error', 'Offline', 'Runtime unavailable');
      if (!state.healthRetryTimer) state.healthRetryTimer = window.setTimeout(() => { state.healthRetryTimer = null; checkHealth(); }, 10000);
      return null;
    }
  }
  async function loadPresets() {
    state.presetsLoading = true;
    state.presetsError = '';
    setText(refs.createPresetStatus, 'Loading workspace options…');
    try {
      const data = await apiRequest('/api/presets');
      state.presets = data && typeof data === 'object' ? data : fallbackPresets;
      setText(refs.createPresetStatus, 'Options ready');
      setText(refs.directionEngineNote, 'Offline mode: local Whisper, with visual-scene ranking when a video has no speech.');
    } catch (error) {
      state.presets = fallbackPresets;
      state.presetsError = error.message || 'The preset service is unavailable.';
      setText(refs.createPresetStatus, 'Using local defaults');
      setText(refs.directionEngineNote, 'Offline mode uses local Whisper and visual-scene fallback for videos without speech.');
    } finally {
      state.presetsLoading = false;
      state.uploadLimitMb = Number(state.presets.upload_max_mb) || 1024;
      setText(refs.createUploadLimit, state.uploadLimitMb === 1024 ? '1GB' : `${state.uploadLimitMb}MB`);
      const subtitles = Object.entries(state.presets.subtitle_presets || {}).map(([id, item]) => ({ id, name: item.name || id.replace(/_/g, ' ') }));
      fillSelect(refs.createCaptionSelect, subtitles, state.create.options.subtitle_preset);
      fillSelect(refs.projectCaptionSelect, subtitles, state.create.options.subtitle_preset);
      fillSelect(refs.createLayoutSelect, state.presets.layout_modes || fallbackPresets.layout_modes, state.create.options.layout_mode);
      fillSelect(refs.projectLayoutSelect, state.presets.layout_modes || fallbackPresets.layout_modes, state.create.options.layout_mode);
      fillSelect(refs.createAspectSelect, state.presets.aspect_ratios || fallbackPresets.aspect_ratios, state.create.options.aspect_ratio);
      fillSelect(refs.projectAspectSelect, state.presets.aspect_ratios || fallbackPresets.aspect_ratios, state.create.options.aspect_ratio);
      if (refs.createClipCountSelect) {
        const max = Math.max(1, Number(state.presets.max_target_clips) || 6);
        refs.createClipCountSelect.innerHTML = Array.from({ length: Math.max(1, max - 2) }, (_, index) => index + 3).map((value) => `<option value="${value}">Top ${value} moments</option>`).join('');
        refs.createClipCountSelect.value = String(Math.min(max, state.create.options.target_clips || 4));
      }
      updateCreateContext();
    }
  }
  function fillSelect(select, options, selected) {
    if (!select || !Array.isArray(options) || !options.length) return;
    select.innerHTML = options.map((option) => `<option value="${escapeAttr(option.id)}">${escapeHtml(option.name || option.id)}</option>`).join('');
    if (selected && options.some((option) => option.id === selected)) select.value = selected;
  }

  async function loadProjects(force = false) {
    if (state.projectsLoading || (state.projectsLoaded && !force)) return state.projects;
    const requestId = ++state.projectsRequestId;
    state.projectsLoading = true;
    state.projectsError = '';
    try {
      const data = await apiRequest('/api/projects?limit=100&offset=0');
      if (requestId !== state.projectsRequestId) return state.projects;
      state.projects = Array.isArray(data.projects) ? data.projects.map(normalizedProject) : [];
      state.projectsLoaded = true;
      state.projectsError = '';
    } catch (error) {
      if (requestId !== state.projectsRequestId) return state.projects;
      state.projectsError = error.message || 'Could not load workspace projects.';
      if (state.route.name === 'library' || state.route.name === 'dashboard') showToast(state.projectsError, 'error');
    } finally { if (requestId === state.projectsRequestId) state.projectsLoading = false; }
    return state.projects;
  }

  function projectStatus(project) { return normalizeStatus(project?.status || 'COMPLETED'); }
  function statusMarkup(status) {
    const normalized = normalizeStatus(status);
    const modifier = normalized === 'COMPLETED' ? '' : isFailedStatus(normalized) ? 'is-failed' : 'is-processing';
    return `<span class="status-text ${modifier}"><i></i>${escapeHtml(normalized.toLowerCase() || 'unknown')}</span>`;
  }
  function projectRow(project, compact = false) {
    const thumb = mediaUrl(project.thumbnail_url);
    const title = project.title || 'Untitled project';
    const clips = Number(project.clips_count || 0);
    const score = project.average_score || '—';
    const row = document.createElement('div');
    row.className = 'project-row';
    row.innerHTML = `<div class="project-thumb-mini">${thumb ? `<img src="${escapeAttr(thumb)}" alt="" loading="lazy">` : '✦'}</div><div class="project-row-main"><strong title="${escapeAttr(title)}">${escapeHtml(title)}</strong><small>${escapeHtml(formatDate(project.created_at))} · ${formatDuration(project.duration)} source</small></div><div class="project-row-meta">${clips} ${clips === 1 ? 'clip' : 'clips'}</div><div class="project-row-score">${escapeHtml(String(score))}${score !== '—' ? '/100 avg' : ''}</div><div>${statusMarkup(project.status)}<button class="row-open" type="button">Open →</button></div>`;
    row.querySelector('.row-open')?.addEventListener('click', () => navigate({ name: 'project', id: project.id }));
    row.addEventListener('dblclick', () => navigate({ name: 'project', id: project.id }));
    return row;
  }
  function renderDashboard() {
    if (refs.dashboardDate) setText(refs.dashboardDate, new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' }).toUpperCase());
    const totalClips = state.projects.reduce((sum, project) => sum + Number(project.clips_count || project.clips?.length || 0), 0);
    const attention = state.projects.filter((project) => isProcessingStatus(projectStatus(project)) || isFailedStatus(projectStatus(project))).length;
    setText(refs.dashboardProjectCount, state.projectsLoaded ? state.projects.length : '—');
    setText(refs.dashboardClipCount, state.projectsLoaded ? totalClips : '—');
    setText(refs.dashboardAttention, state.projectsLoaded ? attention : '—');
    setText(refs.railProjectCount, state.projectsLoaded ? state.projects.length : '—');

    if (!state.projectsLoaded && state.projectsError) {
      refs.dashboardRun.innerHTML = `<div class="state-card state-card--error"><strong>Workspace data is unavailable.</strong><span>${escapeHtml(state.projectsError)}</span><button class="button button--ghost" data-dashboard-retry type="button">Try again</button></div>`;
      refs.dashboardProjectList.innerHTML = `<div class="state-card state-card--error"><strong>Recent work could not load.</strong><span>Retry to reconnect to the project library.</span><button class="button button--ghost" data-dashboard-retry type="button">Retry library</button></div>`;
      qa('[data-dashboard-retry]', refs.dashboardRun).concat(qa('[data-dashboard-retry]', refs.dashboardProjectList)).forEach((button) => button.addEventListener('click', async () => {
        button.disabled = true;
        setText(button, 'Retrying…');
        await loadProjects(true);
        renderDashboard();
      }));
      setText(refs.dashboardNextCopy, 'Reconnect to the workspace to see your latest project and production queue.');
      refs.dashboardNextAction?.setAttribute('data-route', 'dashboard');
      setText(refs.dashboardNextAction, 'Retry workspace →');
      refs.dashboardNextAction?.addEventListener('click', async (event) => { event.preventDefault(); await loadProjects(true); renderDashboard(); }, { once: true });
      return;
    }
    if (!state.projectsLoaded) {
      refs.dashboardRun.innerHTML = '<div class="state-card state-card--loading"><span class="state-spinner" aria-hidden="true"></span><span>Loading your workspace…</span></div>';
      refs.dashboardProjectList.innerHTML = '<div class="state-card state-card--loading"><span class="state-spinner" aria-hidden="true"></span><span>Loading recent work…</span></div>';
      return;
    }

    const activeJob = state.job.snapshot && !jobIsTerminal(state.job.snapshot.status) ? state.job.snapshot : null;
    if (activeJob) {
      const percent = Math.round(Number(activeJob.progress) || 0);
      refs.dashboardRun.innerHTML = `<div class="run-card"><div class="run-card-top"><strong>${escapeHtml(activeJob.source_info?.title || 'Untitled recording')}</strong><span class="run-card-status">${escapeHtml(normalizeStatus(activeJob.status).toLowerCase())}</span></div><p>${escapeHtml(activeJob.message || 'Processing your recording…')}</p><div class="mini-progress"><span style="width:${percent}%"></span></div><div class="run-card-bottom"><span>${percent}% complete</span><button class="text-link" data-route="jobs/${escapeAttr(activeJob.id)}" type="button">Open run →</button></div></div>`;
      refs.dashboardRun.querySelector('[data-route]')?.addEventListener('click', () => navigate({ name: 'job', id: activeJob.id }));
      setText(refs.dashboardNextCopy, 'The engine is working. You can review this run at any time.');
      refs.dashboardNextAction?.setAttribute('data-route', `jobs/${activeJob.id}`);
      setText(refs.dashboardNextAction, 'Open production room →');
    } else if (state.projects.length) {
      const latest = state.projects[0];
      const latestStatus = projectStatus(latest);
      const needsAttention = isFailedStatus(latestStatus);
      const stillWorking = isProcessingStatus(latestStatus);
      const label = needsAttention ? 'Latest run needs attention.' : stillWorking ? 'Latest run is still processing.' : 'Nothing is processing.';
      const copy = needsAttention ? 'Open the project to review the failure details and retry from the saved brief.' : stillWorking ? 'The worker is still preparing this set. Open it to inspect the current status.' : `Your latest set, “${escapeHtml(latest.title || 'Untitled project')}”, is ready for review.`;
      refs.dashboardRun.innerHTML = `<div class="empty-run${needsAttention ? ' empty-run--error' : stillWorking ? ' empty-run--processing' : ''}"><span class="empty-run-mark">${needsAttention ? '!' : stillWorking ? '…' : '✓'}</span><div><strong>${label}</strong><p>${copy}</p></div><button class="button button--ghost" type="button" data-project-open="${escapeAttr(latest.id)}">${needsAttention ? 'Review issue' : stillWorking ? 'Open status' : 'Review set'}</button></div>`;
      refs.dashboardRun.querySelector('[data-project-open]')?.addEventListener('click', () => navigate({ name: 'project', id: latest.id }));
      setText(refs.dashboardNextCopy, needsAttention ? 'Open the latest run to understand what needs a retry.' : stillWorking ? 'Keep the queue moving while the latest set finishes rendering.' : 'Open your latest project and make the final calls on the strongest moments.');
      refs.dashboardNextAction?.setAttribute('data-route', `projects/${latest.id}`);
      setText(refs.dashboardNextAction, needsAttention ? 'Open issue →' : stillWorking ? 'Open status →' : 'Review latest set →');
    } else {
      refs.dashboardRun.innerHTML = '<div class="empty-run"><span class="empty-run-mark">✦</span><div><strong>Your desk is clear.</strong><p>Start with one recording and the first ranked set will land here.</p></div><button class="button button--dark" data-route="create/source" type="button">Create first set</button></div>';
      refs.dashboardRun.querySelector('[data-route]')?.addEventListener('click', () => navigate('create/source'));
      setText(refs.dashboardNextCopy, 'Bring in a recording and let the workspace build your first review queue.');
      refs.dashboardNextAction?.setAttribute('data-route', 'create/source');
      setText(refs.dashboardNextAction, 'Start a production run →');
    }
    refs.dashboardProjectList.innerHTML = '';
    if (!state.projects.length) refs.dashboardProjectList.innerHTML = '<div class="project-list-empty">No projects yet. Your first run will appear here.</div>';
    else state.projects.slice(0, 5).forEach((project) => refs.dashboardProjectList.appendChild(projectRow(project, true)));
  }

  function persistCreateDraft() {
    writeStorage('AI_CLIPPER_CREATE_DRAFT', JSON.stringify({ sourceMode: state.create.sourceMode, url: state.create.url, channel: state.create.channel, options: state.create.options }));
  }
  function clearCreateDraft() { writeStorage('AI_CLIPPER_CREATE_DRAFT', ''); }
  function renderCreate() {
    const step = state.route.step || 'source';
    if (step !== 'source' && !hasSource()) { navigate({ name: 'create', step: 'source' }, true); return; }
    qa('[data-create-panel]').forEach((panel) => panel.classList.toggle('is-current', panel.dataset.createPanel === step));
    qa('[data-create-jump]').forEach((button) => button.classList.toggle('is-current', button.dataset.createJump === step));
    const order = ['source', 'direction', 'review']; const index = order.indexOf(step);
    qa('.stepper-step').forEach((button) => { const buttonIndex = order.indexOf(button.dataset.createJump); button.classList.toggle('is-current', buttonIndex === index); button.classList.toggle('is-done', buttonIndex < index); });
    if (step === 'review') renderCreateReview();
    updateCreateContext();
    setText(refs.createSaveState, hasSource() ? 'Draft saved locally' : 'Start with a source');
    if (state.presetsLoading) setText(refs.createPresetStatus, 'Loading workspace options…');
    else if (state.presetsError) setText(refs.createPresetStatus, 'Using local defaults');
    else setText(refs.createPresetStatus, 'Options ready');
  }
  function normalizedPublicUrl(value) {
    const raw = String(value || '').trim();
    if (!raw) throw new Error('Enter a valid public video URL.');
    const candidate = /^[a-z][a-z\d+.-]*:\/\//i.test(raw) ? raw : `https://${raw}`;
    const parsed = new URL(candidate);
    if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname) throw new Error('Enter a valid public video URL.');
    return candidate;
  }
  function validateSource() {
    if (state.create.sourceMode === 'upload') {
      if (!state.create.file) { showToast('Choose a video file first.', 'error'); return false; }
      return true;
    }
    try { normalizedPublicUrl(state.create.url); return true; }
    catch (_) { showToast('Enter a valid public video URL.', 'error'); refs.createUrlInput?.focus(); return false; }
  }
  function updateCreateContext() {
    const has = hasSource();
    const title = state.create.sourceMode === 'upload' ? (state.create.file?.name || 'No source selected') : (state.create.url ? state.create.url.replace(/^https?:\/\//, '').slice(0, 33) : 'No source selected');
    setText(refs.createContextTitle, title);
    setText(refs.createContextMeta, state.create.sourceMode === 'upload' && state.create.file ? `${(state.create.file.size / (1024 * 1024)).toFixed(1)} MB · local upload` : state.create.url ? 'Public link · metadata pending' : 'Your source will appear here');
    refs.createContextArt?.classList.toggle('has-source', has);
    if (refs.createContextArt && !has) refs.createContextArt.textContent = '✳';
    if (refs.createContextArt && has && state.create.sourceMode === 'url') refs.createContextArt.textContent = '↗';
    const directionDone = Boolean(state.create.options.subtitle_preset && state.create.options.layout_mode);
    const items = refs.createContextList?.querySelectorAll('li') || [];
    [has, directionDone, has && directionDone].forEach((done, index) => { items[index]?.classList.toggle('is-done', done); const label = items[index]?.querySelector('b'); if (label) label.textContent = done ? 'ready' : 'pending'; });
    setText(refs.createContextOutput, `${state.create.options.target_clips || 4} clips`);
    persistCreateDraft();
  }
  function renderCreateReview() {
    const sourceName = state.create.sourceMode === 'upload' ? (state.create.file?.name || 'Upload') : state.create.url.replace(/^https?:\/\//, '');
    const caption = refs.createCaptionSelect?.selectedOptions?.[0]?.textContent || state.create.options.subtitle_preset;
    const layout = refs.createLayoutSelect?.selectedOptions?.[0]?.textContent || state.create.options.layout_mode;
    const ratio = refs.createAspectSelect?.selectedOptions?.[0]?.textContent || state.create.options.aspect_ratio;
    refs.createReviewSummary.innerHTML = `<div class="brief-item"><span>Source</span><strong title="${escapeAttr(sourceName)}">${escapeHtml(sourceName)}</strong><small>${state.create.sourceMode === 'upload' ? 'Local upload' : 'Public URL'}</small></div><div class="brief-item"><span>Output</span><strong>${escapeHtml(`${state.create.options.target_clips} ranked moments`)}</strong><small>${escapeHtml(ratio)}</small></div><div class="brief-item"><span>Caption language</span><strong>${escapeHtml(caption)}</strong><small>Word-level timing</small></div><div class="brief-item"><span>Framing system</span><strong>${escapeHtml(layout)}</strong><small>${escapeHtml(state.create.channel)} channel direction</small></div>`;
    setText(refs.directionEngineNote, state.presetsError ? 'Safe local defaults are active. The configured server engine or local fallback will still process this run.' : 'The run will use the configured server engine or local fallback automatically.');
  }

  function syncCreateOptions() {
    state.create.options.subtitle_preset = refs.createCaptionSelect?.value || 'hormozi';
    state.create.options.layout_mode = refs.createLayoutSelect?.value || 'smart_crop';
    state.create.options.aspect_ratio = refs.createAspectSelect?.value || '9:16';
    state.create.options.target_clips = Number(refs.createClipCountSelect?.value || 4);
    updateCreateContext();
  }
  function handleFile(file) {
    if (!file) return;
    const supported = /\.(mp4|mov|webm)$/i.test(file.name) || String(file.type).startsWith('video/');
    if (!supported) { showToast('Choose an MP4, MOV, or WEBM video.', 'error'); return; }
    if (file.size > state.uploadLimitMb * 1024 * 1024) { showToast(`That file exceeds the ${state.uploadLimitMb}MB workspace limit.`, 'error'); return; }
    state.create.file = file;
    setText(refs.createDropzoneTitle, file.name);
    setText(refs.createUploadMeta, `${(file.size / (1024 * 1024)).toFixed(1)} MB · ready to process`);
    refs.createDropzone?.classList.remove('is-dragging');
    updateCreateContext();
  }

  async function startCreate() {
    if (state.create.submitting) return;
    syncCreateOptions();
    if (!validateSource()) { navigate({ name: 'create', step: 'source' }); return; }
    state.create.submitting = true;
    refs.startCreate.disabled = true;
    refs.startCreate.setAttribute('aria-busy', 'true');
    setText(refs.startCreate, 'Launching…');
    setText(refs.createNotice, '');
    try {
      const sourceUrl = state.create.sourceMode === 'url' ? normalizedPublicUrl(state.create.url) : '';
      const options = { ...state.create.options };
      state.job.lastSubmission = { sourceMode: state.create.sourceMode, url: sourceUrl, file: state.create.file, channel: state.create.channel, options };
      writeStorage('AI_CLIPPER_LAST_SUBMISSION', JSON.stringify({ sourceMode: state.create.sourceMode, url: sourceUrl, channel: state.create.channel, options: state.create.options }));
      let response;
      if (state.create.sourceMode === 'upload') {
        const form = new FormData(); form.append('file', state.create.file); Object.entries(options).forEach(([key, value]) => form.append(key, String(value)));
        response = await apiRequest('/api/upload', { method: 'POST', body: form });
      } else response = await apiRequest('/api/process-url', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: sourceUrl, ...options }) });
      if (!response.job_id) throw new Error('The server did not return a production job.');
      state.job.id = response.job_id; state.job.snapshot = { id: response.job_id, status: response.status || 'QUEUED', progress: 0, message: 'Waiting in queue…' }; state.job.activity = [];
      state.job.settled = false; writeStorage('AI_CLIPPER_ACTIVE_JOB', response.job_id); clearCreateDraft();
      startJobMonitor(response.job_id); navigate({ name: 'job', id: response.job_id }); showToast('Production run launched.');
    } catch (error) {
      setText(refs.createNotice, error.message || 'Could not start the production run.');
      showToast(error.message || 'Could not start the production run.', 'error');
    } finally {
      state.create.submitting = false;
      refs.startCreate.disabled = false;
      refs.startCreate.removeAttribute('aria-busy');
      setText(refs.startCreate, 'Launch production run ↗');
    }
  }

  function restoreCreateSubmission(submission) {
    state.create.sourceMode = submission?.sourceMode === 'upload' ? 'upload' : 'url';
    state.create.url = submission?.url || '';
    state.create.file = submission?.file || null;
    state.create.channel = ['shorts', 'square', 'landscape'].includes(submission?.channel) ? submission.channel : state.create.channel;
    state.create.options = { ...state.create.options, ...(submission?.options || {}) };
    if (refs.createUrlInput) refs.createUrlInput.value = state.create.url;
    qa('[data-source-mode]').forEach((item) => item.classList.toggle('is-selected', item.dataset.sourceMode === state.create.sourceMode));
    qa('[data-channel]').forEach((item) => item.classList.toggle('is-selected', item.dataset.channel === state.create.channel));
    refs.createUrlForm?.classList.toggle('is-hidden', state.create.sourceMode !== 'url');
    refs.createUploadEntry?.classList.toggle('is-hidden', state.create.sourceMode !== 'upload');
    if (state.create.file) {
      setText(refs.createDropzoneTitle, state.create.file.name);
      setText(refs.createUploadMeta, `${(state.create.file.size / (1024 * 1024)).toFixed(1)} MB · ready to process`);
    }
    [refs.createCaptionSelect, refs.createLayoutSelect, refs.createAspectSelect, refs.createClipCountSelect].forEach((select) => {
      if (select) select.value = String(state.create.options[select === refs.createCaptionSelect ? 'subtitle_preset' : select === refs.createLayoutSelect ? 'layout_mode' : select === refs.createAspectSelect ? 'aspect_ratio' : 'target_clips']);
    });
    updateCreateContext();
  }

  async function retryFailedJob() {
    const submission = state.job.lastSubmission;
    if (!submission) {
      showToast('The original brief is no longer available. Start a new run.', 'error');
      navigate({ name: 'create', step: 'source' });
      return;
    }
    restoreCreateSubmission(submission);
    if (state.create.sourceMode === 'upload' && !state.create.file) {
      navigate({ name: 'create', step: 'source' });
      showToast('Re-select the original video to retry this upload.', 'error');
      return;
    }
    navigate({ name: 'create', step: 'review' });
    await startCreate();
  }

  function closeJobMonitor() {
    state.job.eventSource?.close(); state.job.eventSource = null;
    if (state.job.reconnectTimer) window.clearTimeout(state.job.reconnectTimer);
    if (state.job.pollingTimer) window.clearInterval(state.job.pollingTimer);
    state.job.reconnectTimer = null; state.job.pollingTimer = null;
  }
  function clearActiveJobReference() {
    closeJobMonitor();
    state.job.id = '';
    writeStorage('AI_CLIPPER_ACTIVE_JOB', '');
  }
  function jobIsTerminal(status) { return ['COMPLETED', 'FAILED', 'CANCELLED'].includes(normalizeStatus(status)); }
  function startJobMonitor(jobId) {
    if (!jobId) return;
    closeJobMonitor(); state.job.id = jobId; state.job.settled = false; state.job.reconnectAttempts = 0; state.job.pollingFailures = 0; state.job.pollingErrorNotified = false;
    const connect = () => {
      if (state.job.settled || state.job.id !== jobId) return;
      const source = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/stream`); state.job.eventSource = source;
      source.onopen = () => { state.job.reconnectAttempts = 0; state.job.pollingFailures = 0; setText(refs.jobConnectionState, 'Stream connected'); };
      source.onmessage = (event) => { try { updateJobSnapshot(JSON.parse(event.data)); } catch (_) { appendJobActivity('Received an unreadable status update.'); } };
      source.onerror = () => {
        source.close(); state.job.eventSource = null; if (state.job.settled) return;
        state.job.reconnectAttempts += 1; setText(refs.jobConnectionState, `Reconnecting · attempt ${state.job.reconnectAttempts}`);
        if (state.job.reconnectAttempts <= 4) state.job.reconnectTimer = window.setTimeout(connect, Math.min(8000, 900 * (2 ** (state.job.reconnectAttempts - 1))));
        else { setText(refs.jobConnectionState, 'Polling fallback'); beginJobPolling(jobId); }
      };
    };
    connect();
  }
  function beginJobPolling(jobId) {
    if (state.job.pollingTimer) return;
    state.job.pollingFailures = 0;
    state.job.pollingErrorNotified = false;
    state.job.pollingTimer = window.setInterval(async () => {
      try {
        const snapshot = await apiRequest(`/api/jobs/${encodeURIComponent(jobId)}`);
        state.job.pollingFailures = 0;
        state.job.pollingErrorNotified = false;
        setText(refs.jobConnectionState, 'Polling fallback · connected');
        updateJobSnapshot(snapshot);
      } catch (error) {
        if (error.status === 404) {
          state.job.snapshot = { ...(state.job.snapshot || { id: jobId }), status: 'FAILED', progress: 100, message: 'This run was removed.', error: 'The production run is no longer available.' };
          state.job.settled = true;
          clearActiveJobReference();
          showToast('This production run is no longer available.', 'error');
          if (state.route.name === 'job') navigate('dashboard', true);
          return;
        }
        state.job.pollingFailures += 1;
        setText(refs.jobConnectionState, `Polling unavailable · retry ${state.job.pollingFailures}`);
        if (state.job.pollingFailures >= 3 && !state.job.pollingErrorNotified) {
          state.job.pollingErrorNotified = true;
          showToast('Live updates are temporarily unavailable. The worker may still be processing; we will keep retrying.', 'error');
        }
      }
    }, 2800);
  }
  function appendJobActivity(message) {
    if (!message || state.job.activity[state.job.activity.length - 1] === message) return;
    state.job.activity.push(message); if (state.job.activity.length > 35) state.job.activity.shift();
    if (refs.jobActivity) refs.jobActivity.innerHTML = state.job.activity.map((entry) => `<span><span class="activity-time">[${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}]</span>${escapeHtml(entry)}</span>`).join('');
  }
  function updateJobSnapshot(snapshot) {
    if (!snapshot) return;
    state.job.snapshot = snapshot; state.job.id = snapshot.id || state.job.id;
    appendJobActivity(snapshot.message || snapshot.status);
    if (state.route.name === 'job') renderJob();
    if (state.route.name === 'dashboard') renderDashboard();
    if (jobIsTerminal(snapshot.status)) {
      state.job.settled = true; clearActiveJobReference();
      if (normalizeStatus(snapshot.status) === 'COMPLETED') {
        state.selectedProject = normalizedProject(snapshot); loadProjects(true);
        showToast('Your project is ready to review.');
      } else showToast(snapshot.error || 'The production run needs attention.', 'error');
    }
  }
  async function hydrateJob(id) {
    const jobId = id || state.job.id;
    if (!jobId) { navigate('dashboard', true); return; }
    if (!state.job.snapshot || state.job.snapshot.id !== jobId || jobIsTerminal(state.job.snapshot.status)) {
      try { state.job.snapshot = await apiRequest(`/api/jobs/${encodeURIComponent(jobId)}`); }
      catch (error) {
        clearActiveJobReference();
        state.job.snapshot = null;
        showToast(error.status === 404 ? 'This production run was removed or has expired.' : (error.message || 'This run could not be found.'), 'error');
        navigate('dashboard', true);
        return;
      }
    }
    state.job.id = jobId;
    if (!state.job.activity.length) appendJobActivity(state.job.snapshot.message || state.job.snapshot.error || state.job.snapshot.status);
    renderJob();
    if (jobIsTerminal(state.job.snapshot.status)) {
      state.job.settled = true;
      clearActiveJobReference();
    } else startJobMonitor(jobId);
  }
  function renderJob() {
    const job = state.job.snapshot || { id: state.job.id, status: 'QUEUED', progress: 0, message: 'Connecting to the production room…' };
    const status = normalizeStatus(job.status); const percent = Math.max(0, Math.min(100, Math.round(Number(job.progress) || 0)));
    const sourceTitle = job.source_info?.title || state.job.lastSubmission?.url?.replace(/^https?:\/\//, '') || 'Recording';
    setText(refs.jobIdLabel, job.id || 'WAITING'); setText(refs.jobTitle, status === 'COMPLETED' ? 'The set is ready.' : status === 'FAILED' ? 'This run needs attention.' : 'Your run is moving.');
    setText(refs.jobSubtitle, status === 'COMPLETED' ? 'Open the project workspace and make the final calls.' : 'This room stays live while the engine works.');
    setText(refs.jobMessage, job.error || job.message || 'Processing your recording…'); setText(refs.jobProgressPercent, `${percent}%`); setText(refs.jobProgressBar, '');
    if (refs.jobProgressBar) refs.jobProgressBar.style.width = `${percent}%`;
    setText(refs.jobStatusPill, status.toLowerCase()); refs.jobStatusPill?.classList.toggle('is-complete', status === 'COMPLETED'); refs.jobStatusPill?.classList.toggle('is-failed', status === 'FAILED' || status === 'CANCELLED');
    setText(refs.jobDetailId, job.id || '—'); setText(refs.jobDetailSource, sourceTitle); setText(refs.jobDetailOutput, `${job.clips?.length || state.create.options.target_clips || 4} clips`); setText(refs.jobDetailMode, state.create.options.aspect_ratio || '9:16');
    const stageState = jobStageState(status, percent);
    qa('[data-job-stage]', refs.jobStages).forEach((stage) => { const value = stageState[stage.dataset.jobStage] || 0; stage.classList.toggle('is-active', value === 1); stage.classList.toggle('is-complete', value === 2); });
    refs.jobRetry?.classList.toggle('is-hidden', status !== 'FAILED'); refs.jobOpenProject?.classList.toggle('is-hidden', status !== 'COMPLETED');
    setText(refs.jobFooterNote, status === 'COMPLETED' ? 'The render is persisted in your library.' : status === 'FAILED' ? 'Review the error, then retry from the saved brief.' : 'You can leave this room. The worker will keep the run alive.');
    refs.jobOpenProject?.replaceWith(refs.jobOpenProject.cloneNode(true)); refs.jobOpenProject = $('jobOpenProject'); refs.jobOpenProject?.addEventListener('click', () => navigate({ name: 'project', id: job.id }));
  }
  function jobStageState(status, percent) {
    if (status === 'COMPLETED') return { ingest: 2, transcribe: 2, analyze: 2, reframe: 2, render: 2 };
    if (status === 'FAILED' || status === 'CANCELLED') return {};
    if (status === 'TRANSCRIBING') return { ingest: 2, transcribe: 1 };
    if (status === 'ANALYZING') return { ingest: 2, transcribe: 2, analyze: 1 };
    if (status === 'CLIPPING') return { ingest: 2, transcribe: 2, analyze: 2, reframe: percent >= 82 ? 2 : 1, render: percent >= 95 ? 1 : 0 };
    if (status === 'PROCESSING' || status === 'DOWNLOADING' || status === 'QUEUED') return { ingest: 1 };
    return { ingest: 2 };
  }

  function renderProjectLoading() {
    state.selectedProject = null;
    state.selectedClip = null;
    setText(refs.projectTitle, 'Loading project…');
    setText(refs.projectSubtitle, 'Connecting to the project workspace');
    refs.projectStatusDot?.classList.remove('is-processing', 'is-failed');
    setText(refs.projectClipCount, 'Loading…');
    if (refs.projectClipRail) refs.projectClipRail.innerHTML = '<div class="state-card state-card--loading"><span class="state-spinner" aria-hidden="true"></span><span>Loading moments…</span></div>';
  }
  function renderProjectError(message) {
    setText(refs.projectTitle, 'Project unavailable');
    setText(refs.projectSubtitle, message || 'This project could not be loaded.');
    refs.projectStatusDot?.classList.add('is-failed');
    refs.projectDownloadAll?.setAttribute('disabled', 'true');
    if (refs.projectClipRail) refs.projectClipRail.innerHTML = `<div class="state-card state-card--error"><strong>Could not open this project.</strong><span>${escapeHtml(message || 'The project may have been deleted or the runtime is unavailable.')}</span><button class="button button--ghost" data-route="library" type="button">Back to library</button></div>`;
    renderSelectedClip();
  }
  async function loadProject(id) {
    if (state.selectedProject?.id === id) { renderProject(); return; }
    try {
      const project = await apiRequest(`/api/projects/${encodeURIComponent(id)}`);
      if (state.route.name !== 'project' || state.route.id !== id) return;
      state.selectedProject = normalizedProject(project); state.selectedClip = null; renderProject();
    } catch (error) {
      if (state.route.name !== 'project' || state.route.id !== id) return;
      const message = error.message || 'Could not open this project.';
      showToast(message, 'error');
      renderProjectError(message);
    }
  }
  function renderProject() {
    const project = normalizedProject(state.selectedProject); if (!project) return;
    if (state.schedule.projectId !== project.id) { state.schedule.items = []; loadScheduledPosts(project.id); }
    renderScheduledPosts();
    const status = projectStatus(project);
    refs.projectStatusDot?.classList.toggle('is-processing', isProcessingStatus(status));
    refs.projectStatusDot?.classList.toggle('is-failed', isFailedStatus(status));
    setText(refs.projectTitle, project.title); setText(refs.projectSubtitle, `${formatDuration(project.duration)} source · created ${formatDate(project.created_at)}`); setText(refs.projectClipCount, `${project.clips.length} ${project.clips.length === 1 ? 'clip' : 'clips'}`); setText(refs.projectPlayerLabel, project.title.toUpperCase());
    if (refs.projectDownloadAll) {
      refs.projectDownloadAll.disabled = project.clips.length === 0;
      refs.projectDownloadAll.title = project.clips.length ? 'Download all rendered clips' : 'No rendered clips available yet';
    }
    refs.projectClipRail.innerHTML = '';
    project.clips.forEach((clip, index) => {
      const card = document.createElement('button'); card.type = 'button'; card.className = `clip-rail-card${state.selectedClip && clipId(state.selectedClip) === clipId(clip) ? ' is-selected' : ''}`;
      const thumb = mediaUrl(clip.thumbnail_url); card.innerHTML = `<div class="clip-rail-thumb">${thumb ? `<img src="${escapeAttr(thumb)}" alt="" loading="lazy">` : '▶'}<span>${Number(clip.virality_score || 0)}/100</span></div><div class="clip-rail-info"><small>CLIP ${String(index + 1).padStart(2, '0')} · ${formatSeconds(clip.duration)}</small><strong>${escapeHtml(clip.title || 'Untitled moment')}</strong></div>`;
      card.addEventListener('click', () => { selectProjectClip(clip); renderProject(); }); refs.projectClipRail.appendChild(card);
    });
    if (!state.selectedClip || !project.clips.some((clip) => clipId(clip) === clipId(state.selectedClip))) state.selectedClip = project.clips[0] || null;
    renderSelectedClip();
  }
  function selectProjectClip(clip) { state.selectedClip = clip; }
  function renderSelectedClip() {
    const clip = state.selectedClip;
    if (!clip) {
      setText(refs.projectClipTitle, 'No clip selected'); setText(refs.projectScore, '—'); setText(refs.projectHook, 'Select a moment to inspect its hook.'); setText(refs.projectReason, 'The signal rationale will appear here.'); setText(refs.projectQuote, '—'); setText(refs.projectPublishText, 'Select a clip to generate channel copy.'); refs.projectVideo?.removeAttribute('src'); refs.projectVideoEmpty?.classList.remove('is-hidden');
      refs.projectDownloadMain?.removeAttribute('href'); refs.projectDownloadMain?.removeAttribute('download'); refs.projectDownloadMain?.classList.add('is-disabled'); refs.projectDownloadMain?.setAttribute('aria-disabled', 'true'); if (refs.projectDownloadMain) refs.projectDownloadMain.tabIndex = -1;
      if (refs.projectSaveRender) refs.projectSaveRender.disabled = true;
      if (refs.projectOpenWords) refs.projectOpenWords.disabled = true;
      return;
    }
    const url = mediaUrl(clip.video_url); if (refs.projectVideo) { if (url) { refs.projectVideo.src = `${url}${url.includes('?') ? '&' : '?'}v=${Date.now()}`; refs.projectVideo.load(); refs.projectVideoEmpty?.classList.add('is-hidden'); } else { refs.projectVideo.removeAttribute('src'); refs.projectVideoEmpty?.classList.remove('is-hidden'); } }
    setText(refs.projectPlayerFormat, `${clip.aspect_ratio || '9:16'} · ${clip.subtitle_preset === 'none' ? 'no captions' : (clip.subtitle_preset || 'captions')}`); setText(refs.projectClipTitle, clip.title || 'Untitled moment'); setText(refs.projectScore, clip.virality_score ? `${clip.virality_score}` : '—'); setText(refs.projectHook, clip.hook || clip.key_quote || 'Visual moment without speech.'); setText(refs.projectReason, clip.virality_reason || 'Signal rationale was not returned for this clip.'); setText(refs.projectQuote, clip.key_quote || 'No spoken quote in this clip.');
    if (refs.projectDownloadMain) {
      const downloadUrl = clipDownloadUrl(clip);
      if (downloadUrl) {
        refs.projectDownloadMain.href = downloadUrl;
        refs.projectDownloadMain.download = `${(clip.title || 'clip').replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase() || 'clip'}.mp4`;
        refs.projectDownloadMain.classList.remove('is-disabled'); refs.projectDownloadMain.removeAttribute('aria-disabled'); refs.projectDownloadMain.tabIndex = 0;
      } else {
        refs.projectDownloadMain.removeAttribute('href'); refs.projectDownloadMain.removeAttribute('download'); refs.projectDownloadMain.classList.add('is-disabled'); refs.projectDownloadMain.setAttribute('aria-disabled', 'true'); refs.projectDownloadMain.tabIndex = -1;
      }
    }
    if (refs.projectSaveRender) refs.projectSaveRender.disabled = false;
    if (refs.projectOpenWords) refs.projectOpenWords.disabled = false;
    if (refs.projectCaptionSelect) refs.projectCaptionSelect.value = clip.subtitle_preset || 'hormozi'; if (refs.projectLayoutSelect) refs.projectLayoutSelect.value = clip.layout_mode || 'smart_crop'; if (refs.projectAspectSelect) refs.projectAspectSelect.value = clip.aspect_ratio || '9:16';
    const start = Number(clip.start_time) || 0;
    const end = Number(clip.end_time) || start + 30;
    const sourceDuration = Number(state.selectedProject?.duration) || 0;
    const max = sourceDuration > 0 ? sourceDuration : Math.max(end + 15, 30);
    const bounds = clampProjectTrim(start, end, max);
    refs.projectTrimStart.max = String(bounds.max); refs.projectTrimEnd.max = String(bounds.max);
    refs.projectTrimStart.value = String(bounds.start); refs.projectTrimEnd.value = String(bounds.end);
    updateProjectTimeReadout(bounds.start, bounds.end); updatePublishText();
  }
  function clampProjectTrim(start, end, maxValue) {
    const max = Math.max(2, Number(maxValue) || 30);
    let safeStart = Math.max(0, Math.min(Number(start) || 0, max - 2));
    let safeEnd = Math.max(safeStart + 2, Number(end) || safeStart + 2);
    if (safeEnd > max) {
      safeEnd = max;
      safeStart = Math.min(safeStart, Math.max(0, max - 2));
    }
    return { start: safeStart, end: safeEnd, max };
  }
  function updateProjectTimeReadout(start = refs.projectTrimStart?.value, end = refs.projectTrimEnd?.value) { setText(refs.projectTimeReadout, `${formatSeconds(start)} — ${formatSeconds(end)} · ${formatSeconds(Math.max(0, Number(end) - Number(start)))}`); }
  function publishText(clip, platform) {
    if (!clip) return '';
    const title = clip.title || 'A moment worth sharing'; const hook = clip.hook || clip.key_quote || title; const caption = clip.social_caption || 'A visual moment from the video.';
    if (platform === 'youtube') return `${title}\n\n${hook}\n\n${caption}\n\n#Shorts #PodcastClips #Creator`;
    if (platform === 'reels') return `${title}\n\n${caption}\n\nWhat would you add?\n\n#reels #creator #ideas`;
    return `${hook}\n\n${caption}\n\n#fyp #shorts #mindset #creator`;
  }
  function updatePublishText() { setText(refs.projectPublishText, publishText(state.selectedClip, state.currentPlatform) || 'Select a clip to generate channel copy.'); }
  function scheduleDateLabel(value) {
    const date = new Date(String(value || '').endsWith('Z') ? value : `${value}Z`);
    return Number.isNaN(date.getTime()) ? String(value || '') : date.toLocaleString();
  }
  function renderScheduledPosts() {
    if (!refs.scheduledPostList) return;
    const posts = state.schedule.projectId === state.selectedProject?.id ? state.schedule.items : [];
    if (state.schedule.loading && !posts.length) { refs.scheduledPostList.textContent = 'Loading local schedule…'; return; }
    if (!posts.length) { refs.scheduledPostList.textContent = 'No local publishing reminders for this project.'; return; }
    refs.scheduledPostList.innerHTML = posts.map((post) => {
      const ready = post.status === 'READY_TO_PUBLISH';
      const platforms = (post.platforms || []).map((name) => ({ tiktok: 'TikTok', youtube: 'YouTube Shorts', reels: 'Instagram Reels' }[name] || name)).join(' · ');
      return `<article class="scheduled-post"><div><strong>${ready ? 'Ready for manual publishing' : 'Scheduled locally'}</strong><small>${escapeHtml(scheduleDateLabel(post.scheduled_time))} · ${escapeHtml(platforms)}</small></div><button type="button" class="schedule-cancel" data-schedule-id="${escapeAttr(post.id)}" aria-label="Remove scheduled reminder">×</button><p>${ready ? 'Reminder is due. Open each platform and upload the downloaded clip; this offline app does not post for you.' : 'This reminder stays on this computer and will change to ready when its time arrives.'}</p></article>`;
    }).join('');
    qa('[data-schedule-id]', refs.scheduledPostList).forEach((button) => button.addEventListener('click', async () => {
      try { await apiRequest(`/api/scheduled-posts/${encodeURIComponent(button.dataset.scheduleId)}`, { method: 'DELETE' }); await loadScheduledPosts(state.selectedProject?.id); showToast('Local reminder removed.'); }
      catch (error) { showToast(error.message || 'Could not remove reminder.', 'error'); }
    }));
  }
  async function loadScheduledPosts(projectId) {
    if (!projectId) return;
    state.schedule.projectId = projectId; state.schedule.loading = true; renderScheduledPosts();
    try {
      const data = await apiRequest(`/api/scheduled-posts?project_id=${encodeURIComponent(projectId)}`);
      if (state.selectedProject?.id === projectId) state.schedule.items = data.posts || [];
    } catch (error) {
      if (state.selectedProject?.id === projectId) { state.schedule.items = []; setText(refs.scheduleNotice, error.message || 'Could not load local reminders.'); }
    } finally { state.schedule.loading = false; if (state.selectedProject?.id === projectId) renderScheduledPosts(); }
  }
  async function scheduleSelectedClip() {
    if (!state.selectedClip) { showToast('Select a rendered clip first.', 'error'); return; }
    const selected = qa('input[type="checkbox"]:checked', refs.schedulePlatforms).map((input) => input.value);
    if (!selected.length) { showToast('Choose at least one platform.', 'error'); return; }
    const date = new Date(refs.scheduleTime?.value || '');
    if (Number.isNaN(date.getTime()) || date <= new Date()) { showToast('Choose a future date and time.', 'error'); return; }
    refs.scheduleClip.disabled = true;
    try {
      await apiRequest('/api/scheduled-posts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ clip_id: clipId(state.selectedClip), platforms: selected, caption: publishText(state.selectedClip, state.currentPlatform), scheduled_time: date.toISOString() }) });
      setText(refs.scheduleNotice, 'Saved locally. At the scheduled time this becomes a manual publishing reminder.');
      await loadScheduledPosts(state.selectedProject.id); showToast('Local publishing reminder saved.');
    } catch (error) { setText(refs.scheduleNotice, error.message || 'Could not save the reminder.'); showToast(error.message || 'Could not save the reminder.', 'error'); }
    finally { refs.scheduleClip.disabled = false; }
  }
  async function saveProjectRender(customWords) {
    const clip = state.selectedClip; if (!clip) { showToast('Select a clip before re-rendering.', 'error'); return; }
    const trimMax = Number(refs.projectTrimEnd.max) || Number(state.selectedProject.duration) || 30;
    const bounds = clampProjectTrim(refs.projectTrimStart.value, refs.projectTrimEnd.value, trimMax);
    const start = bounds.start; const end = bounds.end;
    refs.projectTrimStart.value = String(start); refs.projectTrimEnd.value = String(end);
    if (end <= start + 1.5) { showToast('Keep at least two seconds between clip boundaries.', 'error'); return; }
    const payload = { subtitle_preset: refs.projectCaptionSelect.value || 'hormozi', layout_mode: refs.projectLayoutSelect.value || 'smart_crop', aspect_ratio: refs.projectAspectSelect.value || '9:16', custom_start: start, custom_end: end };
    if (customWords !== undefined) payload.custom_words = customWords;
    refs.projectSaveRender.disabled = true; setText(refs.projectSaveRender, 'Rendering…');
    try {
      const data = await apiRequest(`/api/clips/${encodeURIComponent(clipId(clip))}/edit`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      state.selectedProject.clips = state.selectedProject.clips.map((item) => clipId(item) === clipId(clip) ? data.clip : item); state.selectedClip = data.clip; renderProject(); showToast('Clip re-rendered and ready.');
    } catch (error) { showToast(error.message || 'The clip could not be re-rendered.', 'error'); }
    finally { refs.projectSaveRender.disabled = false; setText(refs.projectSaveRender, 'Save & re-render'); }
  }
  function openWordsEditor() {
    if (!state.selectedClip || !state.selectedProject) { showToast('Select a clip first.', 'error'); return; }
    const start = Number(state.selectedClip.start_time) || 0; const end = Number(state.selectedClip.end_time) || 30; const words = (state.selectedProject.transcript?.words || []).filter((word) => Number(word.end) > start && Number(word.start) < end);
    refs.wordsList.innerHTML = words.length ? words.map((word) => `<label class="word-chip"><input class="word-editor-input" value="${escapeAttr(word.word || '')}" data-start="${escapeAttr(word.start)}" data-end="${escapeAttr(word.end)}"><small>${formatSeconds(word.start)}</small></label>`).join('') : '<p class="project-list-empty">No word-level transcript is available for this clip.</p>';
    openDialog(refs.wordsDialog);
  }
  async function deleteProject() {
    if (!state.selectedProject) return;
    const confirmed = await askConfirmation('Delete this project?', `“${state.selectedProject.title}” and its rendered artifacts will be permanently removed.`, 'Delete project'); if (!confirmed) return;
    try { await apiRequest(`/api/projects/${encodeURIComponent(state.selectedProject.id)}`, { method: 'DELETE' }); state.selectedProject = null; await loadProjects(true); showToast('Project deleted.'); navigate('library'); } catch (error) { showToast(error.message || 'Could not delete the project.', 'error'); }
  }

  function renderLibrary() {
    if (state.projectsError && !state.projectsLoaded) {
      setText(refs.librarySummaryText, 'Could not load the project inventory.');
      refs.libraryList.innerHTML = `<div class="state-card state-card--error"><strong>Library unavailable.</strong><span>${escapeHtml(state.projectsError)}</span><button class="button button--ghost" type="button" data-library-retry>Retry library</button></div>`;
      refs.libraryList.querySelector('[data-library-retry]')?.addEventListener('click', async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        setText(button, 'Retrying…');
        await loadProjects(true);
        renderLibrary();
      });
      return;
    }
    if (!state.projectsLoaded) {
      setText(refs.librarySummaryText, 'Loading inventory…');
      refs.libraryList.innerHTML = '<div class="state-card state-card--loading"><span class="state-spinner" aria-hidden="true"></span><span>Loading your library…</span></div>';
      return;
    }
    const query = (refs.librarySearch?.value || '').trim().toLowerCase(); const filter = refs.libraryFilter?.value || 'all';
    const projects = state.projects.filter((project) => (!query || String(project.title || '').toLowerCase().includes(query)) && projectMatchesFilter(project, filter));
    setText(refs.librarySummaryText, `${projects.length} of ${state.projects.length} ${state.projects.length === 1 ? 'project' : 'projects'} shown`); refs.libraryList.innerHTML = '';
    if (!projects.length) { refs.libraryList.innerHTML = `<div class="project-list-empty">${state.projects.length ? 'No projects match these filters.' : 'No projects yet. Start a production run to create your first workspace.'}</div>`; return; }
    projects.forEach((project) => refs.libraryList.appendChild(projectRow(project)));
  }

  function setOpsAccess(error = null) {
    const locked = Boolean(error && [401, 403, 503].includes(error.status)); state.admin.unauthorized = locked; refs.opsAccessState?.classList.toggle('is-hidden', !locked);
    if (locked) setText(refs.opsAccessMessage, error.status === 503 ? 'The server requires an ADMIN_API_KEY before Operations can be enabled.' : 'Enter the configured Admin API key in Workspace settings, then refresh.');
  }
  function renderOperationsJobs() {
    const query = (refs.opsJobSearch?.value || '').trim().toLowerCase(); const status = normalizeStatus(refs.opsJobStatus?.value || 'ALL');
    const jobs = state.admin.jobs.filter((job) => (status === 'ALL' || normalizeStatus(job.status) === status) && (!query || `${job.id} ${job.project_title} ${job.source_url}`.toLowerCase().includes(query)));
    refs.opsJobsTable.innerHTML = `<table class="ops-data-table"><thead><tr><th>Job</th><th>Source</th><th>Status</th><th>Progress</th><th></th></tr></thead><tbody>${jobs.length ? jobs.map((job) => { const percent = Math.round(Number(job.progress) || 0); const normalized = normalizeStatus(job.status); const modifier = normalized === 'COMPLETED' ? 'is-good' : normalized === 'FAILED' ? 'is-bad' : 'is-warn'; return `<tr><td><span class="ops-table-id">${escapeHtml(job.id)}</span></td><td><strong>${escapeHtml(job.project_title || job.source_url || 'Video upload')}</strong></td><td><span class="ops-status ${modifier}">${escapeHtml(normalized.toLowerCase())}</span></td><td><div class="ops-bar"><span style="width:${percent}%"></span></div></td><td><button class="row-open ops-delete-job" data-job-id="${escapeAttr(job.id)}" type="button">Remove</button></td></tr>`; }).join('') : '<tr><td colspan="5">No jobs match the current filters.</td></tr>'}</tbody></table>`;
    qa('.ops-delete-job', refs.opsJobsTable).forEach((button) => button.addEventListener('click', async () => { const id = button.dataset.jobId; if (!await askConfirmation('Remove this job?', `Job ${id} will be cancelled and removed from the Operations queue.`, 'Cancel & remove')) return; try { await adminRequest(`delete-${id}`, `/api/admin/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' }); showToast('Job removed.'); await loadOperations(true); } catch (error) { showToast(error.message || 'Could not remove the job.', 'error'); } }));
  }
  function renderOperationsClips() {
    const query = (refs.opsClipSearch?.value || '').trim().toLowerCase(); const clips = state.admin.clips.filter((clip) => !query || `${clip.id} ${clip.title} ${clip.hook} ${clip.project_title}`.toLowerCase().includes(query));
    refs.opsClipsTable.innerHTML = `<table class="ops-data-table"><thead><tr><th>Clip</th><th>Score</th><th>Format</th><th>Length</th><th></th></tr></thead><tbody>${clips.length ? clips.map((clip) => { const url = mediaUrl(clip.video_url); return `<tr><td><strong>${escapeHtml(clip.title || 'Untitled clip')}</strong><small class="ops-table-id">${escapeHtml(clip.project_title || 'Project')}</small></td><td><strong>${Number(clip.virality_score || 0)}/100</strong></td><td>${escapeHtml(clip.aspect_ratio || '9:16')}</td><td>${formatSeconds(clip.duration)}</td><td>${url ? `<a class="row-open" href="${escapeAttr(url)}" target="_blank" rel="noreferrer">Preview</a>` : ''}</td></tr>`; }).join('') : '<tr><td colspan="5">No clips match the current search.</td></tr>'}</tbody></table>`;
  }
  function renderOperationsLogs() {
    const level = refs.opsLogLevel?.value || 'ALL'; const logs = state.admin.logs.filter((log) => level === 'ALL' || log.level === level);
    refs.opsLogConsole.innerHTML = logs.length ? logs.map((log) => `<span class="ops-log-line"><span class="ops-log-time">[${escapeHtml(log.timestamp || '—')}]</span><span class="ops-log-level is-${escapeAttr(String(log.level || 'INFO').toLowerCase())}">[${escapeHtml(log.level || 'INFO')}]</span>${escapeHtml(log.message || '')}</span>`).join('') : 'No events recorded for this level.';
  }
  async function loadOperations(silent = false) {
    if (state.admin.loading) return; state.admin.loading = true; if (refs.opsRefresh) refs.opsRefresh.disabled = true;
    try {
      const results = await Promise.allSettled([adminRequest('metrics', '/api/admin/metrics'), adminRequest('jobs', '/api/admin/jobs?limit=100'), adminRequest('clips', '/api/admin/clips?limit=100'), adminRequest(`logs-${refs.opsLogLevel?.value || 'ALL'}`, `/api/admin/logs?level=${encodeURIComponent(refs.opsLogLevel?.value || 'ALL')}`)]);
      const [metrics, jobs, clips, logs] = results;
      if (metrics.status === 'fulfilled') {
        const data = metrics.value; setOpsAccess(); setText(refs.opsEngineStatus, data.status || 'OPERATIONAL'); setText(refs.opsEngineDetail, `FFmpeg ${data.system?.ffmpeg_available ? 'ready' : 'missing'}`); setText(refs.opsEngineMeta, `${data.system?.environment || 'local'} · uptime ${formatUptime(data.system?.uptime_seconds)}`); setText(refs.opsActiveJobs, data.system?.active_jobs ?? 0); setText(refs.opsWorkerMeta, `${data.system?.active_jobs ?? 0} active · ${data.system?.worker_capacity ?? '—'} workers`); setText(refs.opsStorage, `${data.storage?.app_storage_mb ?? 0} MB`); setText(refs.opsStorageDetail, `Disk free ${data.storage?.disk_free_gb ?? 0} GB`); setText(refs.opsDiskMeta, `DB ${data.storage?.database_kb ?? 0} KB · downloads ${data.storage?.downloads_mb ?? 0} MB`); setText(refs.opsInventory, `${data.stats?.total_clips ?? 0}`); setText(refs.opsInventoryDetail, `${data.stats?.total_projects ?? 0} projects`); setText(refs.opsInventoryMeta, `avg score ${data.stats?.avg_virality_score ?? '—'} · ${data.stats?.total_jobs ?? 0} jobs`);
      } else setOpsAccess(metrics.reason);
      if (jobs.status === 'fulfilled') { state.admin.jobs = jobs.value.jobs || []; renderOperationsJobs(); } else setOpsAccess(jobs.reason);
      if (clips.status === 'fulfilled') { state.admin.clips = clips.value.clips || []; renderOperationsClips(); } else setOpsAccess(clips.reason);
      if (logs.status === 'fulfilled') { state.admin.logs = logs.value.logs || []; renderOperationsLogs(); } else setOpsAccess(logs.reason);
      if (results.some((result) => result.status === 'fulfilled')) { state.admin.lastSync = new Date(); setText(refs.opsSyncStatus, `Synced ${state.admin.lastSync.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`); }
      if (!silent && results.every((result) => result.status === 'rejected') && !state.admin.unauthorized) showToast('Operations data could not be loaded.', 'error');
    } finally { state.admin.loading = false; if (refs.opsRefresh) refs.opsRefresh.disabled = false; }
  }
  function formatUptime(seconds) { const total = Math.max(0, Math.round(Number(seconds) || 0)); const days = Math.floor(total / 86400); const hours = Math.floor((total % 86400) / 3600); const minutes = Math.floor((total % 3600) / 60); return days ? `${days}d ${hours}h` : hours ? `${hours}h ${minutes}m` : `${minutes}m`; }
  function startAdminRefresh() { if (state.admin.refreshTimer || !state.admin.live) return; state.admin.refreshTimer = window.setInterval(() => { if (state.route.name === 'ops') loadOperations(true); }, 30000); }
  function stopAdminRefresh() { if (state.admin.refreshTimer) window.clearInterval(state.admin.refreshTimer); state.admin.refreshTimer = null; }
  async function runMaintenance(button, title, message, endpoint, success) { if (!await askConfirmation(title, message, 'Run action')) return; button.disabled = true; try { const data = await adminRequest(`maintenance-${endpoint}`, endpoint, { method: 'POST' }); showToast(success(data)); await loadOperations(true); } catch (error) { showToast(error.message || 'Maintenance action failed.', 'error'); } finally { button.disabled = false; } }
  function askConfirmation(title, message, confirmLabel) {
    return new Promise((resolve) => { state.confirmResolver = resolve; setText(refs.confirmTitle, title); setText(refs.confirmMessage, message); setText(refs.acceptConfirm, confirmLabel || 'Confirm'); openDialog(refs.confirmDialog); });
  }
  function resolveConfirmation(value) { const resolver = state.confirmResolver; state.confirmResolver = null; closeDialog(refs.confirmDialog); resolver?.(value); }

  function bindSettings() {
    if (refs.settingsAdmin) refs.settingsAdmin.value = readStorage('AI_CLIPPER_ADMIN_KEY');
    const open = () => openDialog(refs.settingsDialog); refs.openSettings?.addEventListener('click', open); refs.topSettings?.addEventListener('click', open); refs.opsOpenSettings?.addEventListener('click', open);
    refs.closeSettings?.addEventListener('click', () => closeDialog(refs.settingsDialog)); refs.cancelSettings?.addEventListener('click', () => closeDialog(refs.settingsDialog)); refs.settingsDialog?.addEventListener('cancel', (event) => { event.preventDefault(); closeDialog(refs.settingsDialog); });
    refs.saveSettings?.addEventListener('click', () => { writeStorage('AI_CLIPPER_ADMIN_KEY', refs.settingsAdmin?.value.trim() || ''); closeDialog(refs.settingsDialog); showToast('Workspace settings saved.'); if (state.route.name === 'ops') loadOperations(); }); bindBackdrop(refs.settingsDialog, () => closeDialog(refs.settingsDialog));
  }
  function bindDialogs() {
    refs.closeConfirm?.addEventListener('click', () => resolveConfirmation(false)); refs.cancelConfirm?.addEventListener('click', () => resolveConfirmation(false)); refs.acceptConfirm?.addEventListener('click', () => resolveConfirmation(true)); refs.confirmDialog?.addEventListener('cancel', (event) => { event.preventDefault(); resolveConfirmation(false); }); bindBackdrop(refs.confirmDialog, () => resolveConfirmation(false));
    refs.closeWords?.addEventListener('click', () => closeDialog(refs.wordsDialog)); refs.cancelWords?.addEventListener('click', () => closeDialog(refs.wordsDialog)); refs.wordsDialog?.addEventListener('cancel', (event) => { event.preventDefault(); closeDialog(refs.wordsDialog); }); refs.saveWords?.addEventListener('click', () => { const words = qa('.word-editor-input', refs.wordsList).map((input) => ({ word: input.value.trim(), start: Number(input.dataset.start), end: Number(input.dataset.end) })).filter((word) => word.word); closeDialog(refs.wordsDialog); saveProjectRender(words); }); bindBackdrop(refs.wordsDialog, () => closeDialog(refs.wordsDialog));
  }
  function bindNavigation() {
    document.addEventListener('click', (event) => { const target = event.target.closest('[data-route]'); if (!target) return; event.preventDefault(); navigate(target.dataset.route); });
    window.addEventListener('hashchange', () => renderRoute(parseRoute())); window.addEventListener('popstate', () => renderRoute(parseRoute()));
    refs.mobileRailToggle?.addEventListener('click', () => { const open = refs.rail.classList.toggle('is-open'); refs.railScrim?.classList.toggle('is-visible', open); refs.mobileRailToggle.setAttribute('aria-expanded', String(open)); });
    refs.railClose?.addEventListener('click', closeMobileRail);
    refs.railScrim?.addEventListener('click', closeMobileRail);
    refs.commandButton?.addEventListener('click', () => navigate('create/source'));
    refs.jobRetry?.addEventListener('click', retryFailedJob);
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && refs.rail?.classList.contains('is-open')) { closeMobileRail(); return; } if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); navigate('create/source'); } if (event.key.toLowerCase() === 'n' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) { event.preventDefault(); navigate('create/source'); } });
  }
  function bindCreate() {
    qa('[data-source-mode]').forEach((button) => button.addEventListener('click', () => { state.create.sourceMode = button.dataset.sourceMode; qa('[data-source-mode]').forEach((item) => item.classList.toggle('is-selected', item === button)); refs.createUrlForm.classList.toggle('is-hidden', state.create.sourceMode !== 'url'); refs.createUploadEntry.classList.toggle('is-hidden', state.create.sourceMode !== 'upload'); updateCreateContext(); }));
    refs.createUrlInput?.addEventListener('input', () => { state.create.url = refs.createUrlInput.value; updateCreateContext(); });
    refs.createUrlForm?.addEventListener('submit', (event) => { event.preventDefault(); if (validateSource()) navigate({ name: 'create', step: 'direction' }); });
    refs.sourceContinue?.addEventListener('click', () => { if (validateSource()) navigate({ name: 'create', step: 'direction' }); }); refs.uploadContinue?.addEventListener('click', () => { if (validateSource()) navigate({ name: 'create', step: 'direction' }); });
    qa('[data-example-url]').forEach((button) => button.addEventListener('click', () => { state.create.sourceMode = 'url'; state.create.url = button.dataset.exampleUrl || ''; refs.createUrlInput.value = state.create.url; qa('[data-source-mode]').forEach((item) => item.classList.toggle('is-selected', item.dataset.sourceMode === 'url')); refs.createUrlForm.classList.remove('is-hidden'); refs.createUploadEntry.classList.add('is-hidden'); updateCreateContext(); }));
    refs.createDropzone?.addEventListener('click', () => refs.createFileInput?.click()); refs.createFileInput?.addEventListener('change', () => handleFile(refs.createFileInput.files?.[0])); refs.createDropzone?.addEventListener('dragover', (event) => { event.preventDefault(); refs.createDropzone.classList.add('is-dragging'); }); refs.createDropzone?.addEventListener('dragleave', () => refs.createDropzone.classList.remove('is-dragging')); refs.createDropzone?.addEventListener('drop', (event) => { event.preventDefault(); handleFile(event.dataTransfer?.files?.[0]); });
    const channelAspectRatios = { shorts: '9:16', square: '1:1', landscape: '16:9' };
    qa('[data-channel]').forEach((button) => button.addEventListener('click', () => {
      state.create.channel = button.dataset.channel;
      qa('[data-channel]').forEach((item) => item.classList.toggle('is-selected', item === button));
      const ratio = channelAspectRatios[state.create.channel];
      if (ratio) {
        state.create.options.aspect_ratio = ratio;
        if (refs.createAspectSelect) refs.createAspectSelect.value = ratio;
      }
      updateCreateContext();
    }));
    [refs.createCaptionSelect, refs.createLayoutSelect, refs.createAspectSelect, refs.createClipCountSelect].forEach((select) => select?.addEventListener('change', syncCreateOptions));
    qa('[data-create-jump]').forEach((button) => button.addEventListener('click', () => { const step = button.dataset.createJump; if (step === 'direction' && !hasSource()) { showToast('Choose a source before setting direction.', 'error'); navigate({ name: 'create', step: 'source' }); return; } if (step === 'review') syncCreateOptions(); navigate({ name: 'create', step }); }));
    refs.startCreate?.addEventListener('click', startCreate);
  }
  async function downloadResource(url, filename) {
    if (!url) throw new ApiError('This file is not available yet.', 404);
    let response;
    try { response = await fetch(url, { credentials: 'same-origin' }); }
    catch (error) { throw new ApiError(error.message || 'The download could not be started.', 0); }
    if (!response.ok) {
      let message = `Download failed (${response.status})`;
      try { const data = await response.json(); message = data.detail || data.message || message; } catch (_) { /* Keep the status fallback. */ }
      throw new ApiError(message, response.status);
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = filename || 'ai-clipper-download';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }
  async function handleClipDownload(event) {
    event.preventDefault();
    const clip = state.selectedClip;
    const url = clipDownloadUrl(clip);
    if (!clip || !url) { showToast('Select a rendered clip before downloading.', 'error'); return; }
    const button = refs.projectDownloadMain;
    if (button?.classList.contains('is-busy')) return;
    button?.classList.add('is-busy');
    setText(button, 'Preparing download…');
    try {
      const filename = button.download || 'clip.mp4';
      await downloadResource(url, filename);
      showToast('Clip download started.');
    } catch (error) { showToast(error.message || 'The clip could not be downloaded.', 'error'); }
    finally { button?.classList.remove('is-busy'); if (button) button.innerHTML = 'Download MP4 <span>↓</span>'; }
  }
  async function downloadProjectArchive() {
    if (!state.selectedProject?.clips?.length) { showToast('There are no rendered clips to download yet.', 'error'); return; }
    const button = refs.projectDownloadAll;
    if (button?.disabled) return;
    button.disabled = true;
    setText(button, 'Preparing ZIP…');
    try {
      await downloadResource(`/api/projects/${encodeURIComponent(state.selectedProject.id)}/download-all`, `${(state.selectedProject.title || 'clips').replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase() || 'clips'}.zip`);
      showToast('ZIP download started.');
    } catch (error) { showToast(error.message || 'The project archive could not be downloaded.', 'error'); }
    finally { button.disabled = false; button.innerHTML = 'Download set <span>↓</span>'; }
  }
  function bindProject() {
    refs.projectDelete?.addEventListener('click', deleteProject);
    refs.projectDownloadAll?.addEventListener('click', downloadProjectArchive);
    refs.projectDownloadMain?.addEventListener('click', handleClipDownload);
    refs.projectCopyButton?.addEventListener('click', () => refs.projectCopyText?.click()); refs.projectSaveRender?.addEventListener('click', () => saveProjectRender()); refs.projectOpenWords?.addEventListener('click', openWordsEditor);
    [refs.projectTrimStart, refs.projectTrimEnd].forEach((input) => input?.addEventListener('input', () => {
      const bounds = clampProjectTrim(refs.projectTrimStart.value, refs.projectTrimEnd.value, refs.projectTrimEnd.max);
      refs.projectTrimStart.value = String(bounds.start);
      refs.projectTrimEnd.value = String(bounds.end);
      updateProjectTimeReadout(bounds.start, bounds.end);
    }));
    [refs.projectCaptionSelect, refs.projectLayoutSelect, refs.projectAspectSelect].forEach((select) => select?.addEventListener('change', () => { if (state.selectedClip) state.selectedClip = { ...state.selectedClip }; }));
    qa('[data-publish-platform]').forEach((button) => button.addEventListener('click', () => { qa('[data-publish-platform]').forEach((item) => item.classList.remove('is-selected')); button.classList.add('is-selected'); state.currentPlatform = button.dataset.publishPlatform || 'tiktok'; updatePublishText(); }));
    refs.projectCopyText?.addEventListener('click', async () => { if (!state.selectedClip) { showToast('Select a clip first.', 'error'); return; } try { await copyText(publishText(state.selectedClip, state.currentPlatform)); showToast(`${state.currentPlatform} copy copied.`); } catch (_) { showToast('Could not copy the publish text.', 'error'); } });
    refs.scheduleClip?.addEventListener('click', scheduleSelectedClip);
  }
  function bindLibrary() { refs.librarySearch?.addEventListener('input', renderLibrary); refs.libraryFilter?.addEventListener('change', renderLibrary); refs.libraryRefresh?.addEventListener('click', async () => { await loadProjects(true); renderLibrary(); showToast('Library refreshed.'); }); }
  function bindOperations() {
    refs.opsRefresh?.addEventListener('click', async () => { await loadOperations(); if (!state.admin.unauthorized) showToast('Operations synced.'); }); refs.opsLiveRefresh?.addEventListener('change', () => { state.admin.live = refs.opsLiveRefresh.checked; if (state.admin.live && state.route.name === 'ops') startAdminRefresh(); else stopAdminRefresh(); showToast(state.admin.live ? 'Live refresh enabled.' : 'Live refresh paused.'); }); refs.opsJobSearch?.addEventListener('input', renderOperationsJobs); refs.opsJobStatus?.addEventListener('change', renderOperationsJobs); refs.opsClipSearch?.addEventListener('input', renderOperationsClips); refs.opsLogLevel?.addEventListener('change', () => loadOperations(true)); refs.opsRefreshLogs?.addEventListener('click', () => loadOperations(true));
    refs.opsPurge?.addEventListener('click', () => runMaintenance(refs.opsPurge, 'Clear source cache?', 'Unreferenced source files will be removed. Active projects and jobs are protected.', '/api/admin/maintenance/purge-downloads', (data) => `Cleared ${data.files_removed || 0} source files.`)); refs.opsVacuum?.addEventListener('click', () => runMaintenance(refs.opsVacuum, 'Vacuum the database?', 'SQLite will reclaim unused pages. This does not delete projects.', '/api/admin/maintenance/vacuum-db', (data) => `Database vacuumed · ${data.db_size_kb || 0} KB.`)); refs.opsClearJobs?.addEventListener('click', () => runMaintenance(refs.opsClearJobs, 'Clear finished jobs?', 'Completed, failed, and cancelled queue records will be removed.', '/api/admin/maintenance/clear-jobs', (data) => `Cleared ${data.cleared_count || 0} finished jobs.`));
  }
  function copyText(text) {
    if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text);
    const area = document.createElement('textarea'); area.value = text; area.style.position = 'fixed'; area.style.opacity = '0'; document.body.appendChild(area); area.select(); document.execCommand('copy'); area.remove(); return Promise.resolve();
  }

  bindNavigation(); bindSettings(); bindDialogs(); bindCreate(); bindProject(); bindLibrary(); bindOperations();
  loadPresets(); checkHealth();
  window.setInterval(() => { if (state.route.name === 'project') loadScheduledPosts(state.selectedProject?.id); }, 30000);
  const savedDraft = readStorage('AI_CLIPPER_CREATE_DRAFT');
  if (savedDraft) {
    try { restoreCreateSubmission(JSON.parse(savedDraft)); } catch (_) { clearCreateDraft(); }
  }
  const savedSubmission = readStorage('AI_CLIPPER_LAST_SUBMISSION');
  if (savedSubmission) {
    try {
      const saved = JSON.parse(savedSubmission);
      const safeOptions = { ...(saved.options || {}) };
      delete safeOptions.gemini_api_key;
      delete safeOptions.groq_api_key;
      state.job.lastSubmission = { ...saved, options: safeOptions };
      writeStorage('AI_CLIPPER_LAST_SUBMISSION', JSON.stringify({ ...state.job.lastSubmission, file: undefined }));
      restoreCreateSubmission(state.job.lastSubmission);
    } catch (_) { writeStorage('AI_CLIPPER_LAST_SUBMISSION', ''); }
  }
  renderRoute(parseRoute());
  if (state.job.id) {
    hydrateJob(state.job.id).then(() => { if (state.route.name === 'dashboard') renderDashboard(); }).catch((error) => showToast(error.message || 'The saved production run could not be restored.', 'error'));
  }
});
