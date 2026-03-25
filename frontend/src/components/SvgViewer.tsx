export function SvgViewer({ svg }: { svg: string }) {
  return <div className="svg-stage" dangerouslySetInnerHTML={{ __html: svg }} />
}
