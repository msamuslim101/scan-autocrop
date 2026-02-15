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
    dropZoneSection.style.display = 'none';
    resultsSection.style.display = 'block';

    // Stats
    statTotal.textContent = data.total;
    statCropped.textContent = data.cropped;
    statUnchanged.textContent = data.unchanged;
    statRate.textContent = `${data.success_rate}%`;
    resultsCount.textContent = `${data.total} images processed`;

    setStatus(`Done - ${data.success_rate}% cropped`);

    // Strategy badges
    strategyBreakdown.innerHTML = '';
    for (const [strategy, count] of Object.entries(data.stats)) {
        const badge = document.createElement('span');
        badge.className = 'strategy-badge';
        badge.innerHTML = `${formatStrategy(strategy)} <span class="count">${count}</span>`;
        strategyBreakdown.appendChild(badge);
    }

    // Image cards
    imageGrid.innerHTML = '';
    for (const result of data.results) {
        const card = createImageCard(result);
        imageGrid.appendChild(card);
    }
}

function showFolderResults(data) {
    dropZoneSection.style.display = 'none';
    resultsSection.style.display = 'block';

    statTotal.textContent = data.total;
    statCropped.textContent = data.cropped;
    statUnchanged.textContent = data.total - data.cropped;
    statRate.textContent = `${data.success_rate}%`;
    resultsCount.textContent = `Saved to: ${data.output_folder}`;

    setStatus(`Done - ${data.success_rate}% cropped`);

    // Strategy badges
    strategyBreakdown.innerHTML = '';
    for (const [strategy, count] of Object.entries(data.stats)) {
        const badge = document.createElement('span');
        badge.className = 'strategy-badge';
        badge.innerHTML = `${formatStrategy(strategy)} <span class="count">${count}</span>`;
        strategyBreakdown.appendChild(badge);
    }

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
