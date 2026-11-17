# Exploratory schema assumption

The initial read-only shape inspection treated PUBLIC_REQUESTS.producer_archive as a path string. The original field is a dictionary containing path, index and hash. Python raised TypeError before any product or evidence writes. The corrected inspection reads the path entry, and the independent checker validates that dictionary against the actual INDEX row.

This error occurred in an exploratory shell snippet before the independent checker was created. Its exception was `TypeError: argument should be a str or an os.PathLike object where __fspath__ returns a str, not 'dict'`. All author artifacts remained untouched. The first executable independent checker passed its initial 5050 assertions. The final checker adds exact public scope and witness-pixel table checks.
