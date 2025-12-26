"""Tests for file handling with container pooling.

These tests verify that generated files are correctly retrieved from containers
when container pooling is enabled.
"""

import pytest
import aiohttp
import ssl
import os

# Test configuration
API_URL = os.getenv("TEST_API_URL", "https://localhost")
API_KEY = os.getenv("TEST_API_KEY", "test-api-key-for-development-only")


@pytest.fixture
def ssl_context():
    """Create SSL context that doesn't verify certificates for local testing."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


@pytest.fixture
def headers():
    """API headers."""
    return {"X-API-Key": API_KEY, "Content-Type": "application/json"}


class TestFileGeneration:
    """Test file generation and retrieval."""

    @pytest.mark.asyncio
    async def test_generated_image_is_valid_png(self, ssl_context, headers):
        """Test that generated PNG files are correctly retrieved with full content."""
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Generate a matplotlib image
            payload = {
                "lang": "py",
                "code": """
import matplotlib.pyplot as plt
plt.figure(figsize=(6, 4))
plt.plot([1, 2, 3, 4], [1, 4, 9, 16], 'ro-')
plt.title('Test Chart')
plt.savefig('/mnt/data/test_chart.png', dpi=100)
print('Chart saved')
""",
                "entity_id": "test-file-gen-png"
            }

            async with session.post(
                f"{API_URL}/exec", json=payload, headers=headers, ssl=ssl_context
            ) as resp:
                assert resp.status == 200
                result = await resp.json()

                # Verify file was detected
                files = result.get("files", [])
                assert len(files) >= 1, "Expected at least one generated file"

                file_info = files[0]
                assert file_info.get("name") == "test_chart.png"
                assert file_info.get("id") is not None

                session_id = result.get("session_id")
                file_id = file_info.get("id")

                # Download the file
                download_url = f"{API_URL}/download/{session_id}/{file_id}"
                async with session.get(
                    download_url, headers=headers, ssl=ssl_context
                ) as dl_resp:
                    assert dl_resp.status == 200
                    content = await dl_resp.read()

                    # Verify it's a valid PNG (minimum reasonable size)
                    assert len(content) > 1000, f"File too small: {len(content)} bytes"

                    # Check PNG magic bytes
                    assert content[:8] == b'\x89PNG\r\n\x1a\n', "Not a valid PNG file"

    @pytest.mark.asyncio
    async def test_multiple_generated_files(self, ssl_context, headers):
        """Test that multiple generated files are all correctly retrieved."""
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            payload = {
                "lang": "py",
                "code": """
import matplotlib.pyplot as plt
import numpy as np

# Create 3 different plots
for name in ['alpha', 'beta', 'gamma']:
    plt.figure()
    plt.plot(np.random.randn(10))
    plt.title(f'{name} plot')
    plt.savefig(f'/mnt/data/{name}.png')
    print(f'Created {name}.png')
""",
                "entity_id": "test-multi-files"
            }

            async with session.post(
                f"{API_URL}/exec", json=payload, headers=headers, ssl=ssl_context
            ) as resp:
                assert resp.status == 200
                result = await resp.json()

                files = result.get("files", [])
                assert len(files) >= 3, f"Expected 3 files, got {len(files)}"

                session_id = result.get("session_id")
                filenames = {f.get("name") for f in files}

                # Verify all expected files are present
                assert "alpha.png" in filenames
                assert "beta.png" in filenames
                assert "gamma.png" in filenames

                # Download each file and verify
                for file_info in files:
                    download_url = f"{API_URL}/download/{session_id}/{file_info['id']}"
                    async with session.get(
                        download_url, headers=headers, ssl=ssl_context
                    ) as dl_resp:
                        assert dl_resp.status == 200
                        content = await dl_resp.read()

                        assert len(content) > 1000, (
                            f"File {file_info['name']} too small: {len(content)} bytes"
                        )
                        assert content[:4] == b'\x89PNG', (
                            f"File {file_info['name']} is not a valid PNG"
                        )

    @pytest.mark.asyncio
    async def test_text_file_generation(self, ssl_context, headers):
        """Test that text files are correctly generated and retrieved."""
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            payload = {
                "lang": "py",
                "code": """
# Write a text file
with open('/mnt/data/output.txt', 'w') as f:
    f.write('Hello, World!\\n')
    f.write('This is a test file.\\n')
print('Text file created')
""",
                "entity_id": "test-text-file"
            }

            async with session.post(
                f"{API_URL}/exec", json=payload, headers=headers, ssl=ssl_context
            ) as resp:
                assert resp.status == 200
                result = await resp.json()

                files = result.get("files", [])
                assert len(files) >= 1, "Expected at least one generated file"

                # Find the text file
                txt_file = next(
                    (f for f in files if f.get("name") == "output.txt"), None
                )
                assert txt_file is not None, "output.txt not found in generated files"

                session_id = result.get("session_id")

                # Download and verify content
                download_url = f"{API_URL}/download/{session_id}/{txt_file['id']}"
                async with session.get(
                    download_url, headers=headers, ssl=ssl_context
                ) as dl_resp:
                    assert dl_resp.status == 200
                    content = await dl_resp.text()

                    assert "Hello, World!" in content
                    assert "This is a test file." in content

    @pytest.mark.asyncio
    async def test_csv_file_generation(self, ssl_context, headers):
        """Test that CSV files are correctly generated and retrieved."""
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            payload = {
                "lang": "py",
                "code": """
import pandas as pd

df = pd.DataFrame({
    'name': ['Alice', 'Bob', 'Charlie'],
    'age': [25, 30, 35],
    'city': ['NYC', 'LA', 'Chicago']
})
df.to_csv('/mnt/data/people.csv', index=False)
print(f'Created CSV with {len(df)} rows')
""",
                "entity_id": "test-csv-file"
            }

            async with session.post(
                f"{API_URL}/exec", json=payload, headers=headers, ssl=ssl_context
            ) as resp:
                assert resp.status == 200
                result = await resp.json()

                files = result.get("files", [])
                csv_file = next(
                    (f for f in files if f.get("name") == "people.csv"), None
                )
                assert csv_file is not None, "people.csv not found"

                session_id = result.get("session_id")

                # Download and verify
                download_url = f"{API_URL}/download/{session_id}/{csv_file['id']}"
                async with session.get(
                    download_url, headers=headers, ssl=ssl_context
                ) as dl_resp:
                    assert dl_resp.status == 200
                    content = await dl_resp.text()

                    assert "name,age,city" in content
                    assert "Alice" in content
                    assert "Bob" in content
                    assert "Charlie" in content


class TestFileHandlingWithPooling:
    """Test file handling specifically with container pooling enabled."""

    @pytest.mark.asyncio
    async def test_file_generation_after_pool_acquisition(self, ssl_context, headers):
        """Test that files are correctly retrieved when container comes from pool."""
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Use unique entity_id to get a fresh session/container from pool
            import time
            entity_id = f"test-pool-file-{int(time.time())}"

            payload = {
                "lang": "py",
                "code": """
import matplotlib.pyplot as plt
plt.figure()
plt.pie([30, 40, 30], labels=['A', 'B', 'C'])
plt.savefig('/mnt/data/pie.png')
print('Pie chart created')
""",
                "entity_id": entity_id
            }

            async with session.post(
                f"{API_URL}/exec", json=payload, headers=headers, ssl=ssl_context
            ) as resp:
                assert resp.status == 200
                result = await resp.json()

                files = result.get("files", [])
                assert len(files) >= 1, "No files generated"

                pie_file = next((f for f in files if "pie" in f.get("name", "")), None)
                assert pie_file is not None, "pie.png not found"

                session_id = result.get("session_id")

                # Download and verify it's a real PNG
                download_url = f"{API_URL}/download/{session_id}/{pie_file['id']}"
                async with session.get(
                    download_url, headers=headers, ssl=ssl_context
                ) as dl_resp:
                    assert dl_resp.status == 200
                    content = await dl_resp.read()

                    # Should be a substantial PNG file, not a stub
                    assert len(content) > 5000, (
                        f"File appears truncated: {len(content)} bytes"
                    )
                    assert content[:8] == b'\x89PNG\r\n\x1a\n', "Invalid PNG"

    @pytest.mark.asyncio
    async def test_large_file_generation(self, ssl_context, headers):
        """Test that large generated files are correctly retrieved."""
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            payload = {
                "lang": "py",
                "code": """
import matplotlib.pyplot as plt
import numpy as np

# Create a large, detailed plot
fig, axes = plt.subplots(2, 2, figsize=(12, 10), dpi=150)

for ax in axes.flat:
    x = np.linspace(0, 10, 1000)
    for i in range(10):
        ax.plot(x, np.sin(x + i * 0.5) + np.random.randn(1000) * 0.1)

plt.tight_layout()
plt.savefig('/mnt/data/large_plot.png')
print('Large plot created')
""",
                "entity_id": "test-large-file"
            }

            async with session.post(
                f"{API_URL}/exec", json=payload, headers=headers, ssl=ssl_context
            ) as resp:
                assert resp.status == 200
                result = await resp.json()

                files = result.get("files", [])
                large_file = next(
                    (f for f in files if f.get("name") == "large_plot.png"), None
                )
                assert large_file is not None, "large_plot.png not found"

                session_id = result.get("session_id")

                # Download and verify
                download_url = f"{API_URL}/download/{session_id}/{large_file['id']}"
                async with session.get(
                    download_url, headers=headers, ssl=ssl_context
                ) as dl_resp:
                    assert dl_resp.status == 200
                    content = await dl_resp.read()

                    # Large detailed plot should be > 50KB
                    assert len(content) > 50000, (
                        f"Large file too small: {len(content)} bytes"
                    )
                    assert content[:8] == b'\x89PNG\r\n\x1a\n', "Invalid PNG"
