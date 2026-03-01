/**
 * Scan Auto-Crop — Frontend App
 * Handles drag-and-drop upload, API calls, and result rendering.
 */

const API = '';  // Same-origin

// ---------------------------------------------------------------------------
// DOM Elements
// ---------------------------------------------------------------------------
const dropZone = document.getElementById('dropZone');
const dropZoneSection = document.getElementById('dropZoneSection');
const fileInput = document.getElementById('fileInput');
const folderPathInput = document.getElementById('folderPathInput');
const folderCropBtn = document.getElementById('folderCropBtn');
const resultsSection = document.getElementById('resultsSection');
const imageGrid = document.getElementById('imageGrid');
const statsBar = document.getElementById('statsBar');
const strategyBreakdown = document.getElementById('strategyBreakdown');
const progressOverlay = document.getElementById('progressOverlay');
const progressTitle = document.getElementById('progressTitle');
const progressText = document.getElementById('progressText');
const progressBar = document.getElementById('progressBar');
const backBtn = document.getElementById('backBtn');
const headerStatus = document.getElementById('headerStatus');

// Stat elements
const statTotal = document.getElementById('statTotal');
const statCropped = document.getElementById('statCropped');
const statUnchanged = document.getElementById('statUnchanged');
const statRate = document.getElementById('statRate');
const resultsCount = document.getElementById('resultsCount');

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let currentSessionId = null;
let lastCropData = null;  // Store for export

// ---------------------------------------------------------------------------
// Strategy Glossary
// ---------------------------------------------------------------------------
const STRATEGY_INFO = {
    pro_contour: {
        label: 'Pro Contour',
        desc: 'Primary method. Used Otsu thresholding to separate the photo from the scanner background, then found the outermost contour shape. The irregular contour was used directly as the crop boundary. This is the most common and reliable strategy.'
    },
    pro_rect: {
        label: 'Pro Rect',
        desc: 'Same Otsu detection as Pro Contour, but the contour approximated to a clean 4-sided rectangle. Produces a tighter, more geometrically precise crop. Works best on well-aligned scans with clean borders.'
    },
    canny_edge: {
        label: 'Canny Edge',
        desc: 'Fallback for when Otsu fails (e.g. snow photos, white-on-white). Uses gradient-based edge detection to find physical borders regardless of fill color. Catches images that the primary method misses.'
    },
    variance: {
        label: 'Variance',
        desc: 'Detects photo regions by measuring local pixel variance. Scanner backgrounds have near-zero variance (flat color), while real photos have texture and detail. Used when both Otsu and Canny fail.'
    },
    saturation: {
        label: 'Saturation',
        desc: 'Uses color saturation to separate content from background. Scanner beds produce pure neutral gray (zero saturation), while even the palest real photos have slight color. Last resort before gradient scan.'
    },
    gradient: {
        label: 'Gradient',
        desc: 'Final fallback. Scans from each edge inward looking for the first row or column with significant gradient changes, indicating a physical photo boundary. Used when all other methods fail.'
    },
    original: {
        label: 'Original (Unchanged)',
        desc: 'No crop was applied. This means all 5 strategies determined that the image either has no detectable border to remove, or the detected region was too close to the original size to justify cropping. The original file was saved as-is to prevent data loss.'
    },
    no_crop_needed: {
        label: 'No Crop Needed',
        desc: 'The engine determined that the image does not have a scanner border. The original was kept unchanged.'
    },
    error_fallback: {
        label: 'Error Fallback',
        desc: 'An unexpected error occurred during processing. The original image was saved as-is to prevent any data loss.'
    }
};

// ---------------------------------------------------------------------------
// Event Listeners
// ---------------------------------------------------------------------------

// Click to upload
dropZone.addEventListener('click', () => fileInput.click());

// File selection
fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFileUpload(Array.from(e.target.files));
    }
});

// Drag & Drop
dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('drag-over');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');

    const files = [];
    if (e.dataTransfer.items) {
        for (const item of e.dataTransfer.items) {
            if (item.kind === 'file') {
                const file = item.getAsFile();
                if (file && isImageFile(file.name)) {
                    files.push(file);
                }
            }
        }
    } else {
        for (const file of e.dataTransfer.files) {
            if (isImageFile(file.name)) {
                files.push(file);
            }
        }
    }

    if (files.length > 0) {
        handleFileUpload(files);
    }
});

// Folder crop button
folderCropBtn.addEventListener('click', () => {
    const path = folderPathInput.value.trim();
    if (path) {
        handleFolderCrop(path);
    }
});

// Enter key on folder input
folderPathInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        folderCropBtn.click();
    }
});

// Back button
backBtn.addEventListener('click', resetView);

// Export report button
document.getElementById('exportBtn').addEventListener('click', exportReport);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function isImageFile(name) {
    const ext = name.split('.').pop().toLowerCase();
    return ['jpg', 'jpeg', 'png', 'bmp', 'tif', 'tiff'].includes(ext);
}

function setStatus(text, active = true) {
    headerStatus.innerHTML = `
        <span class="status-dot" style="${active ? '' : 'animation: none; background: var(--text-muted);'}"></span>
        <span>${text}</span>
    `;
}

function showProgress(title, text) {
    progressTitle.textContent = title;
    progressText.textContent = text;
    progressBar.style.width = '30%';
    progressOverlay.style.display = 'flex';
}

function updateProgress(text, percent) {
    progressText.textContent = text;
    if (percent !== undefined) {
        progressBar.style.width = `${percent}%`;
    }
}

function hideProgress() {
    progressOverlay.style.display = 'none';
}

function resetView() {
    resultsSection.style.display = 'none';
    dropZoneSection.style.display = 'flex';
    imageGrid.innerHTML = '';
    strategyBreakdown.innerHTML = '';
    fileInput.value = '';
    currentSessionId = null;
    setStatus('Ready');
}

// ---------------------------------------------------------------------------
// File Upload Flow
// ---------------------------------------------------------------------------
async function handleFileUpload(files) {
    showProgress('Uploading...', `Sending ${files.length} images to the server`);
    setStatus('Uploading...');

    try {
        // Step 1: Upload
        const formData = new FormData();
        files.forEach(f => formData.append('files', f));

        const uploadRes = await fetch(`${API}/api/upload`, {
            method: 'POST',
            body: formData,
        });

        if (!uploadRes.ok) throw new Error('Upload failed');
        const uploadData = await uploadRes.json();
        currentSessionId = uploadData.session_id;

        updateProgress('Cropping...', `Processing ${uploadData.count} images with 5-tier engine`);
        setStatus('Processing...');

        // Step 2: Crop
        const cropForm = new FormData();
        cropForm.append('session_id', currentSessionId);

        const cropRes = await fetch(`${API}/api/crop`, {
            method: 'POST',
            body: cropForm,
        });

        if (!cropRes.ok) throw new Error('Crop failed');
        const cropData = await cropRes.json();

        updateProgress('Done!', 'Rendering results...');
        progressBar.style.width = '100%';

        // Short delay to show 100%
        await new Promise(r => setTimeout(r, 400));
        hideProgress();

        // Step 3: Show results
        showResults(cropData);

    } catch (err) {
        hideProgress();
        setStatus('Error', false);
        console.error('Processing error:', err);
        alert(`Error: ${err.message}`);
    }
}

// ---------------------------------------------------------------------------
// Folder Crop Flow
// ---------------------------------------------------------------------------
async function handleFolderCrop(folderPath) {
    showProgress('Processing Folder...', `Cropping images in: ${folderPath}`);
    setStatus('Processing folder...');

    try {
        const formData = new FormData();
        formData.append('folder_path', folderPath);

        const res = await fetch(`${API}/api/crop-folder`, {
            method: 'POST',
            body: formData,
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Folder crop failed');
        }

        const data = await res.json();

        updateProgress('Done!', `Saved to: ${data.output_folder}`);
        progressBar.style.width = '100%';
        await new Promise(r => setTimeout(r, 600));
        hideProgress();

        // Show results (folder mode doesn't have thumbnails but still shows stats)
        showFolderResults(data);

    } catch (err) {
        hideProgress();
        setStatus('Error', false);
        console.error('Folder crop error:', err);
        alert(`Error: ${err.message}`);
    }
}

// ---------------------------------------------------------------------------
// Render Results
// ---------------------------------------------------------------------------
function showResults(data) {
    lastCropData = data;
    dropZoneSection.style.display = 'none';
    resultsSection.style.display = 'block';

    // Stats
    statTotal.textContent = data.total;
    statCropped.textContent = data.cropped;
    statUnchanged.textContent = data.unchanged;
    statRate.textContent = `${data.success_rate}%`;
    resultsCount.textContent = `${data.total} images processed`;

    setStatus(`Done - ${data.success_rate}% cropped`);

    // Strategy badges with tooltips
    renderStrategyBadges(data.stats);

    // Image cards
    imageGrid.innerHTML = '';
    for (const result of data.results) {
        const card = createImageCard(result);
        imageGrid.appendChild(card);
    }
}

function showFolderResults(data) {
    lastCropData = data;
    dropZoneSection.style.display = 'none';
    resultsSection.style.display = 'block';

    statTotal.textContent = data.total;
    statCropped.textContent = data.cropped;
    statUnchanged.textContent = data.total - data.cropped;
    statRate.textContent = `${data.success_rate}%`;
    resultsCount.textContent = `Saved to: ${data.output_folder}`;

    setStatus(`Done - ${data.success_rate}% cropped`);

    // Strategy badges with tooltips
    renderStrategyBadges(data.stats);

    // Image cards (folder mode - no thumbnails, just info)
    imageGrid.innerHTML = '';
    for (const result of data.results) {
        const card = createFolderCard(result);
        imageGrid.appendChild(card);
    }
}

function createImageCard(result) {
    const card = document.createElement('div');
    card.className = 'image-card';

    const isChanged = result.strategy !== 'original' && result.strategy !== 'no_crop_needed';
    const sizeText = result.cropped_size
        ? `${result.cropped_size[0]}x${result.cropped_size[1]}`
        : '';

    card.innerHTML = `
        <div class="image-card-compare">
            <img src="data:image/jpeg;base64,${result.original_thumbnail}" alt="Original">
            <img src="data:image/jpeg;base64,${result.cropped_thumbnail}" alt="Cropped">
            <span class="image-card-label label-before">Before</span>
            <span class="image-card-label label-after">After</span>
        </div>
        <div class="image-card-info">
            <div class="image-card-name" title="${result.filename}">${result.filename}</div>
            <div class="image-card-meta">
                <span class="image-card-strategy ${isChanged ? '' : 'strategy-original'}">${result.strategy}</span>
                <span class="image-card-size">${sizeText}</span>
            </div>
        </div>
        <div class="image-card-actions">
            <a href="${API}/api/download/${currentSessionId}/${result.filename}" 
               download="${result.filename}"
               class="btn btn-ghost btn-sm" style="width: 100%; justify-content: center;">
                Download
            </a>
        </div>
    `;

    return card;
}

function createFolderCard(result) {
    const card = document.createElement('div');
    card.className = 'image-card';

    const isChanged = result.strategy !== 'original' && result.strategy !== 'no_crop_needed';
    const origText = result.original_size
        ? `${result.original_size[0]}x${result.original_size[1]}`
        : '';
    const cropText = result.cropped_size
        ? `${result.cropped_size[0]}x${result.cropped_size[1]}`
        : '';

    card.innerHTML = `
        <div class="image-card-info" style="padding-top: 20px;">
            <div class="image-card-name" title="${result.filename}">${result.filename}</div>
            <div class="image-card-meta">
                <span class="image-card-strategy ${isChanged ? '' : 'strategy-original'}">${result.strategy}</span>
                <span class="image-card-size">${origText} → ${cropText}</span>
            </div>
        </div>
    `;

    return card;
}

function formatStrategy(str) {
    return str.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

// ---------------------------------------------------------------------------
// Strategy Badge Rendering (with tooltips)
// ---------------------------------------------------------------------------
function renderStrategyBadges(stats) {
    strategyBreakdown.innerHTML = '';
    for (const [strategy, count] of Object.entries(stats)) {
        const badge = document.createElement('span');
        badge.className = 'strategy-badge has-tooltip';

        const info = STRATEGY_INFO[strategy];
        const tooltip = info ? info.desc : '';
        badge.setAttribute('data-tooltip', tooltip);

        badge.innerHTML = `${formatStrategy(strategy)} <span class="count">${count}</span>`;
        strategyBreakdown.appendChild(badge);
    }
}

// ---------------------------------------------------------------------------
// Export Report
// ---------------------------------------------------------------------------
function exportReport() {
    if (!lastCropData) return;

    const d = lastCropData;
    const now = new Date().toLocaleString();
    const lines = [];

    lines.push('='.repeat(60));
    lines.push('  SCAN AUTO-CROP REPORT');
    lines.push('='.repeat(60));
    lines.push(`Generated: ${now}`);
    if (d.output_folder) lines.push(`Output:    ${d.output_folder}`);
    lines.push('');

    lines.push('SUMMARY');
    lines.push('-'.repeat(40));
    lines.push(`Total images:    ${d.total}`);
    lines.push(`Cropped:         ${d.cropped}`);
    lines.push(`Unchanged:       ${d.total - d.cropped}`);
    lines.push(`Success rate:    ${d.success_rate}%`);
    lines.push('');

    lines.push('STRATEGY BREAKDOWN');
    lines.push('-'.repeat(40));
    for (const [strategy, count] of Object.entries(d.stats)) {
        const pct = ((count / d.total) * 100).toFixed(1);
        const info = STRATEGY_INFO[strategy];
        const label = info ? info.label : formatStrategy(strategy);
        lines.push(`  ${label.padEnd(22)} ${String(count).padStart(4)}  (${pct}%)`);
    }
    lines.push('');

    lines.push('STRATEGY GLOSSARY');
    lines.push('-'.repeat(40));
    for (const [strategy, count] of Object.entries(d.stats)) {
        const info = STRATEGY_INFO[strategy];
        if (info) {
            lines.push(`[${info.label}]`);
            lines.push(`  ${info.desc}`);
            lines.push('');
        }
    }

    lines.push('PER-IMAGE RESULTS');
    lines.push('-'.repeat(40));
    lines.push(`${'Filename'.padEnd(28)} ${'Strategy'.padEnd(16)} ${'Original'.padEnd(12)} ${'Cropped'.padEnd(12)}`);
    lines.push('-'.repeat(70));

    for (const r of d.results) {
        const orig = r.original_size ? `${r.original_size[0]}x${r.original_size[1]}` : 'N/A';
        const crop = r.cropped_size ? `${r.cropped_size[0]}x${r.cropped_size[1]}` : 'N/A';
        lines.push(`${r.filename.padEnd(28)} ${r.strategy.padEnd(16)} ${orig.padEnd(12)} ${crop.padEnd(12)}`);
    }

    lines.push('');
    lines.push('='.repeat(60));
    lines.push('  Scan Auto-Crop by @msamuslim101');
    lines.push('  https://github.com/msamuslim101/scan-autocrop');
    lines.push('='.repeat(60));

    // Download as .txt
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `crop-report-${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
}
