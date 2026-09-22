import React from 'react'

// A deliberately small Markdown subset for model output: fenced code, inline
// code, bold, headings and bullets. Everything is returned as React elements
// with the text as children, so React escapes it — there is no
// dangerouslySetInnerHTML anywhere in this app and no markup is ever built
// from model- or GitHub-supplied strings.

function formatInline(line, keyPrefix) {
  return line.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/g).map((part, index) => {
    const key = `${keyPrefix}-${index}`
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return <code key={key} className="md-inline-code">{part.slice(1, -1)}</code>
    }
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={key}>{part.slice(2, -2)}</strong>
    }
    return part
  })
}

function renderCodeBlock(part, key) {
  const inner = part.slice(3, -3)
  const lines = inner.split('\n')
  // Drop a bare language tag on the first line; leaving it in renders a stray
  // "python" line inside the block.
  const body = /^[a-zA-Z0-9_+-]*$/.test(lines[0].trim()) ? lines.slice(1).join('\n') : inner
  return (
    <pre key={key} className="md-code-block">
      <code>{body.replace(/^\n+|\n+$/g, '')}</code>
    </pre>
  )
}

export function formatMessageText(text) {
  if (!text) return ''

  return text.split(/(```[\s\S]*?```)/g).map((part, index) => {
    // A truncated response leaves an unterminated fence. Treating it as a code
    // block anyway ran slice(3, -3) over ordinary text and silently ate the
    // last three characters.
    if (part.startsWith('```') && part.endsWith('```') && part.length >= 6) {
      return renderCodeBlock(part, index)
    }

    return (
      <span key={index} className="md-text">
        {part.split('\n').map((line, lineIndex) => {
          const heading = line.match(/^(#{1,4})\s+(.*)$/)
          const bullet = line.match(/^(\s*)[-*]\s+(.*)$/)

          let content
          if (heading) {
            content = <strong className="md-heading">{formatInline(heading[2], `${index}-${lineIndex}`)}</strong>
          } else if (bullet) {
            content = (
              <span className="md-bullet" style={{ paddingLeft: bullet[1].length * 6 }}>
                <span aria-hidden="true">•</span>
                <span>{formatInline(bullet[2], `${index}-${lineIndex}`)}</span>
              </span>
            )
          } else {
            content = formatInline(line, `${index}-${lineIndex}`)
          }

          return (
            <React.Fragment key={lineIndex}>
              {lineIndex > 0 && '\n'}
              {content}
            </React.Fragment>
          )
        })}
      </span>
    )
  })
}
