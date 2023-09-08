# Documentation

This `doc` folder is the future location of documentation for Subiquity.   This
will be used to migrate the official documentation to readthedocs, and later
will be the home of that documentation.

The `../documentation` folder is the existing location for this sort of
documentation.  As the RTD version is not yet ready, documentation changes
should be made to `../documentation` until this README is updated to say
otherwise.  As such, please make any desired documentation changes to
`../documentation`.

# Local preview

To build this documentation, you can run `make install` from this folder to
create the virtual environment. 

Then run the `make run` command, which will build a html version of the docs,
and serve the docs in the virtual environment. This is very convenient if you
are working on them and want your saved changes to be reflected as a working
preview.
