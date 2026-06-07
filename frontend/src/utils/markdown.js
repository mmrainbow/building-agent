/** 统一的 Markdown → HTML 渲染器。stripHtml=true 时移除所有 HTML 标签（巡检/历史用）。 */
export function renderMarkdown(text, { stripHtml = false } = {}) {
  if (!text) return ''
  let html = text
  // 清理噪音
  html = html.replace(/!\[.*?\]\(data:image[^)]*(?:\))?/g, '')
  html = html.replace(/(?<!<img[^>]*?)data:image\S+/g, '')

  if (stripHtml) {
    // 巡检/历史：不存在有意义的内嵌 HTML，全部转义
    html = html.replace(/<div[^>]*>/gi, '').replace(/<\/div>/gi, '')
    html = html.replace(/<img[^>]*>/gi, '')
    html = html.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  } else {
    // 聊天：保留 <img> 标签
    html = html.replace(/<\/?div[^>]*>/gi, '')
    const imgs = []
    html = html.replace(/<img[^>]+>/gi, m => { imgs.push(m); return `\x00IMG${imgs.length - 1}\x00` })
    html = html.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    html = html.replace(/\x00IMG(\d+)\x00/g, (_, i) => imgs[+i])
  }

  // Markdown → HTML
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/((?:^- .+\n?)+)/gm, m =>
    '<ul>' + m.trim().split('\n').map(l => '<li>' + l.replace(/^- /, '') + '</li>').join('') + '</ul>')
  html = html.replace(/((?:^\d+\. .+\n?)+)/gm, m =>
    '<ol>' + m.trim().split('\n').map(l => '<li>' + l.replace(/^\d+\. /, '') + '</li>').join('') + '</ol>')
  html = html.replace(/\n\n+/g, '</p><p>').replace(/\n/g, '<br>')
  html = '<p>' + html + '</p>'
  return html.replace(/<p><\/p>/g, '').replace(/<p>(<[ou]l>)/g, '$1').replace(/(<\/[ou]l>)<\/p>/g, '$1')
}

export function isHtmlContent(text) {
  return /<img|<div|<pre|<p|<[ou]l|<h[1-4]|!\[/i.test(text || '')
}
