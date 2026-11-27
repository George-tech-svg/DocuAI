import { jsPDF } from 'jspdf';

/** Combine selected camera/gallery JPG and PNG files into a small ordered PDF. */
export async function combinePhotosIntoPdf(photos: File[]): Promise<File> {
  if (!photos.length) throw new Error('Choose at least one photo.');
  const firstBitmap = await createImageBitmap(photos[0]);
  const firstOrientation = firstBitmap.width > firstBitmap.height ? 'landscape' : 'portrait';
  firstBitmap.close();
  const pdf = new jsPDF({ orientation: firstOrientation, unit: 'mm', format: 'a4', compress: true });
  for (const [index, photo] of photos.entries()) {
    const bitmap = await createImageBitmap(photo);
    const scale = Math.min(1, 2000 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext('2d');
    if (!context) {
      bitmap.close();
      throw new Error('This photo could not be prepared. Please try a JPG or PNG image.');
    }
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const orientation = canvas.width > canvas.height ? 'landscape' : 'portrait';
    if (index > 0) pdf.addPage('a4', orientation);
    const pageWidth = orientation === 'landscape' ? 297 : 210;
    const pageHeight = orientation === 'landscape' ? 210 : 297;
    const fit = Math.min(pageWidth / canvas.width, pageHeight / canvas.height);
    const imageWidth = canvas.width * fit;
    const imageHeight = canvas.height * fit;
    pdf.addImage(canvas.toDataURL('image/jpeg', 0.82), 'JPEG', (pageWidth - imageWidth) / 2, (pageHeight - imageHeight) / 2, imageWidth, imageHeight, undefined, 'FAST');
    canvas.width = 1;
    canvas.height = 1;
  }
  const baseName = photos[0].name.replace(/\.[^.]+$/, '').replace(/[^a-z0-9_-]+/gi, '-') || 'photos';
  return new File([pdf.output('blob')], `${baseName}-photos.pdf`, { type: 'application/pdf' });
}
