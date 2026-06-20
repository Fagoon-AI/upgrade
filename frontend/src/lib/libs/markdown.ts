import MarkdownIt from 'markdown-it'
import { jsPDF } from 'jspdf'

export function downloadMarkdownAsPDF(markdown: string) {
  const md = new MarkdownIt()
  
  const cleanedMarkdown = markdown.replace(/<think>[\s\S]*?<\/think>/g, '')
    .replace(/&lt;think&gt;[\s\S]*?&lt;\/think&gt;/g, '')
    .replace(/&lt;think>[\s\S]*?&lt;\/think>/g, ''); 
  let html = md.render(cleanedMarkdown)
  
  html = html
    .replace(/<h1>/g, '<h1 style="color: black; font-size: 24pt; font-weight: bold; margin: 20pt 0 10pt 0;">')
    .replace(/<h2>/g, '<h2 style="color: black; font-size: 18pt; font-weight: bold; margin: 16pt 0 8pt 0;">')
    .replace(/<h3>/g, '<h3 style="color: black; font-size: 16pt; font-weight: bold; margin: 14pt 0 6pt 0;">')
    .replace(/<p>/g, '<p style="color: black; font-size: 14pt; line-height: 1.6; margin: 8pt 0;">')
    .replace(/<li>/g, '<li style="color: black; font-size: 14pt; margin: 4pt 0;">')
    .replace(/<code>/g, '<code style="color: black; font-family: monospace; font-size: 12pt; background-color: #f5f5f5; padding: 2pt 4pt; border-radius: 3pt;">')
    .replace(/<strong>/g, '<strong style="color: black; font-weight: bold;">')
    .replace(/<em>/g, '<em style="color: black; font-style: italic;">')

  const fullHTML = `
    <html>
      <body style="font-family: Arial, sans-serif; color: black; background-color: white; margin: 0; padding: 20pt;">
        ${html}
      </body>
    </html>
  `
  
  const doc = new jsPDF({ unit: 'pt', format: 'a4' })
  doc.html(fullHTML, {
    callback: (doc) => doc.save('markdown.pdf'),
    x: 40,
    y: 40,
    width: 520,
    windowWidth: 800
  })
}