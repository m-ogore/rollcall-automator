document.getElementById('course-form').addEventListener('submit', function(e) {
    e.preventDefault();
    const name = document.getElementById('course-name').value;
    const url = document.getElementById('course-url').value;
    fetch('/api/set_course', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name, url })
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById('response').innerText = data.message;
    })
    .catch(error => {
        document.getElementById('response').innerText = 'Error setting course.';
    });
});

document.getElementById('csv-form').addEventListener('submit', function(e) {
    e.preventDefault();
    const fileInput = document.getElementById('csv-file');
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    fetch('/api/upload_csv', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById('response').innerText = data.message;
    })
    .catch(error => {
        document.getElementById('response').innerText = 'Error uploading CSV.';
    });
});
