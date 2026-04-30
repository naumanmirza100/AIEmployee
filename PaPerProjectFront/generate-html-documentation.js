import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const resultsPath = path.join(__dirname, 'screenshots-results.json');
const results = JSON.parse(fs.readFileSync(resultsPath, 'utf8'));

function generateHTMLDocumentation() {
  let html = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pay Per Project - Complete Documentation</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: white;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        header {
            text-align: center;
            padding: 40px 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            margin: -20px -20px 40px -20px;
        }
        h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        h2 {
            font-size: 2em;
            color: #667eea;
            margin: 40px 0 20px 0;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
        }
        h3 {
            font-size: 1.5em;
            color: #555;
            margin: 30px 0 15px 0;
        }
        .toc {
            background: #f9f9f9;
            padding: 30px;
            margin: 30px 0;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        .toc h2 {
            margin-top: 0;
            border-bottom: none;
        }
        .toc ul {
            list-style: none;
            columns: 2;
            column-gap: 30px;
        }
        .toc li {
            margin: 10px 0;
            break-inside: avoid;
        }
        .toc a {
            color: #667eea;
            text-decoration: none;
            font-size: 1.1em;
        }
        .toc a:hover {
            text-decoration: underline;
        }
        .page-section {
            margin: 50px 0;
            padding: 30px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .route {
            font-style: italic;
            color: #888;
            margin-bottom: 20px;
        }
        .description {
            background: #f0f7ff;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
            border-left: 4px solid #667eea;
        }
        .screenshot-container {
            margin: 30px 0;
            text-align: center;
        }
        .screenshot-container img {
            max-width: 100%;
            height: auto;
            border: 2px solid #ddd;
            border-radius: 8px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        .page-break {
            page-break-before: always;
            border-top: 2px dashed #ccc;
            margin-top: 50px;
            padding-top: 50px;
        }
        footer {
            text-align: center;
            padding: 30px;
            margin-top: 50px;
            color: #888;
            border-top: 2px solid #eee;
        }
        @media print {
            .page-break {
                page-break-before: always;
            }
        }
    </style>
</head>
<body>
    <div class="container" >
        <header>
            <h1>Pay Per Project</h1>
            <p style="font-size: 1.3em; margin-top: 10px;">Complete Project Documentation</p>
            <p style="margin-top: 10px; opacity: 0.9;">Generated: ${new Date().toLocaleDateString()}</p>
        </header>

        <div class="toc">
            <h2>Table of Contents</h2>
            <ul>
`;

  results.forEach((page, index) => {
    html += `                <li><a href="#page-${index + 1}">${index + 1}. ${page.name} - ${page.route}</a></li>\n`;
  });

  html += `            </ul>
        </div>

`;

  results.forEach((page, index) => {
    const screenshotBase64 = page.screenshotPath && fs.existsSync(page.screenshotPath)
      ? fs.readFileSync(page.screenshotPath).toString('base64')
      : null;

    html += `        <div class="page-section" id="page-${index + 1}">
            ${index > 0 ? '<div class="page-break"></div>' : ''}
            <h2>${index + 1}. ${page.name}</h2>
            <p class="route">Route: ${page.route}</p>
            
            <div class="description">
                <h3>Description:</h3>
                <p>${page.description || 'No description available.'}</p>
            </div>

            <div class="screenshot-container">
                <h3>Screenshot:</h3>
                ${screenshotBase64
      ? `<img src="data:image/png;base64,${screenshotBase64}" alt="${page.name} Screenshot" />`
      : `<p style="color: red;">Screenshot not available${page.error ? ': ' + page.error : ''}</p>`
    }
            </div>
        </div>

`;
  });

  html += `        <footer>
            <p>Pay Per Project Documentation - ${results.length} Pages</p>
            <p>Generated on ${new Date().toLocaleString()}</p>
        </footer>
    </div>
</body>
</html>`;

  const outputPath = path.join(__dirname, 'PayPerProject_Documentation.html');
  fs.writeFileSync(outputPath, html);
  console.log(`\n✓ HTML Documentation generated successfully!`);
  console.log(`  Output: ${outputPath}`);
  console.log(`  Total pages documented: ${results.length}`);
  console.log(`\n💡 Tip: Open this HTML file in any web browser for easy viewing.`);
  console.log(`   You can also print it to PDF from the browser.`);
}

generateHTMLDocumentation();



