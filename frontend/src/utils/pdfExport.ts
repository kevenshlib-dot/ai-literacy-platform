import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'

type ExportElementToPdfOptions = {
  filename: string
  backgroundColor?: string | null
  marginMm?: number
  scale?: number
  imageQuality?: number
}

export async function exportElementToPdf(
  element: HTMLElement,
  {
    filename,
    backgroundColor = '#f0f2f5',
    marginMm = 10,
    scale = 1.5,
    imageQuality = 0.78,
  }: ExportElementToPdfOptions,
) {
  const canvas = await html2canvas(element, {
    scale,
    useCORS: true,
    backgroundColor,
  })

  const pdf = new jsPDF('p', 'mm', 'a4')
  const pageWidthMm = 210
  const pageHeightMm = 297
  const contentWidthMm = pageWidthMm - marginMm * 2
  const contentHeightMm = pageHeightMm - marginMm * 2
  const pageCanvasHeight = Math.floor((canvas.width * contentHeightMm) / contentWidthMm)
  const pageCanvas = document.createElement('canvas')
  const pageContext = pageCanvas.getContext('2d')

  if (!pageContext || pageCanvasHeight <= 0) {
    throw new Error('PDF渲染失败')
  }

  pageCanvas.width = canvas.width

  let sourceY = 0
  let pageIndex = 0
  while (sourceY < canvas.height) {
    const sliceHeight = Math.min(pageCanvasHeight, canvas.height - sourceY)
    pageCanvas.height = sliceHeight
    pageContext.clearRect(0, 0, pageCanvas.width, pageCanvas.height)

    if (backgroundColor) {
      pageContext.fillStyle = backgroundColor
      pageContext.fillRect(0, 0, pageCanvas.width, pageCanvas.height)
    }

    pageContext.drawImage(
      canvas,
      0,
      sourceY,
      canvas.width,
      sliceHeight,
      0,
      0,
      canvas.width,
      sliceHeight,
    )

    if (pageIndex > 0) {
      pdf.addPage()
    }

    const imgData = pageCanvas.toDataURL('image/jpeg', imageQuality)
    const sliceHeightMm = (sliceHeight * contentWidthMm) / canvas.width
    pdf.addImage(
      imgData,
      'JPEG',
      marginMm,
      marginMm,
      contentWidthMm,
      sliceHeightMm,
      undefined,
      'FAST',
    )

    sourceY += sliceHeight
    pageIndex += 1
  }

  pdf.save(filename)
}
