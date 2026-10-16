"""Short-lived PDF parser; never imports application settings or credentials."""
import io
import json
import os
import sys


def main():
    if os.name != 'nt':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    from pypdf import PdfReader, apply_configuration
    data = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise ValueError('PDF too large')
    with apply_configuration(maximum_declared_stream_length=4_000_000,
                             array_based_stream_maximum_output_length=4_000_000,
                             zlib_maximum_output_length=4_000_000,
                             lzw_maximum_output_length=4_000_000,
                             run_length_maximum_output_length=4_000_000,
                             image_maximum_buffer_size=4_000_000,
                             page_tree_maximum_entries=100,
                             xform_maximum_invocations_per_extraction=100):
        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > 50:
            raise ValueError('Too many PDF pages')
        pages = []
        total = 0
        for page in reader.pages:
            text = (page.extract_text() or '').strip()
            total += len(text)
            if total > 400000:
                raise ValueError('Too much PDF text')
            pages.append(text)
        sys.stdout.write(json.dumps(pages))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Do not print untrusted document data or parser internals.
        sys.exit(2)
