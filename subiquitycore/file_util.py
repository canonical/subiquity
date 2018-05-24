import os
import stat
import tempfile

_DEF_PERMS = 0o644


def write_file(filename, content, mode=None, omode="wb", copy_mode=False):
    """Atomically write filename.
    open filename in mode 'omode', write content, chmod to 'mode'.
    """
    if mode is None:
        mode = _DEF_PERMS
    if copy_mode:
        try:
            file_stat = os.stat(filename)
            mode = stat.S_IMODE(file_stat.st_mode)
        except OSError:
            pass

    tf = None
    try:
        tf = tempfile.NamedTemporaryFile(dir=os.path.dirname(filename),
                                         delete=False, mode=omode)
        tf.write(content)
        tf.close()
        os.chmod(tf.name, mode)
        os.rename(tf.name, filename)
    except OSError as e:
        if tf is not None:
            os.unlink(tf.name)
        raise e
