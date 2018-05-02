#include <Python.h>
#include <ctype.h>
#include <errno.h>

#include <netlink/cache.h>
#include <netlink/route/addr.h>
#include <netlink/route/link.h>
#include <netlink/route/route.h>

#define NL_CB_me NL_CB_DEFAULT

static char *act2str(int act) {
#define C2S(x)					\
	case x:					\
		return &#x[7]
	switch (act) {
		C2S(NL_ACT_UNSPEC);
		C2S(NL_ACT_NEW);
		C2S(NL_ACT_DEL);
		C2S(NL_ACT_GET);
		C2S(NL_ACT_SET);
		C2S(NL_ACT_CHANGE);
	default:
		return "???";
	}
#undef C2S
}

struct Listener {
	PyObject_HEAD
	struct nl_cache_mngr *mngr;
	struct nl_cache *link_cache;
	PyObject *observer;
	PyObject *exc_typ, *exc_val, *exc_tb;
};

static void observe_link_change(
	int act,
	struct rtnl_link *link,
	struct Listener* listener)
{
	if (listener->exc_typ != NULL || listener->observer == Py_None) {
		return;
	}
	PyObject *data;
	data = Py_BuildValue(
		"{si sI sI si}",
		"ifindex", rtnl_link_get_ifindex(link),
		"flags", rtnl_link_get_flags(link),
		"arptype", rtnl_link_get_arptype(link),
		"family", rtnl_link_get_family(link));
	if (data == NULL) {
		goto exit;
	}
	if (rtnl_link_get_name(link) != NULL) {
		PyObject *ob = PyBytes_FromString(rtnl_link_get_name(link));
		if (ob == NULL || PyDict_SetItemString(data, "name", ob) < 0) {
			Py_XDECREF(ob);
			goto exit;
		}
		Py_DECREF(ob);
	}
	PyObject *r = PyObject_CallMethod(listener->observer, "link_change", "sO", act2str(act), data);
	Py_XDECREF(r);

  exit:
	Py_XDECREF(data);
	if (PyErr_Occurred()) {
		PyErr_Fetch(&listener->exc_typ, &listener->exc_val, &listener->exc_tb);
	}
}

static void _cb_link(struct nl_cache *cache, struct nl_object *ob, int act,
                    void *data) {
	observe_link_change(act, (struct rtnl_link *)ob, (struct Listener*)data);
}

static void _e_link(struct nl_object *ob, void *data) {
	observe_link_change(NL_ACT_NEW, (struct rtnl_link *)ob, (struct Listener*)data);
}

static void observe_addr_change(
	int act,
	struct rtnl_addr *addr,
	struct Listener* listener)
{
	if (listener->exc_typ != NULL || listener->observer == Py_None) {
		return;
	}
	PyObject *data;
	data = Py_BuildValue(
		"{si sI si si}",
		"ifindex", rtnl_addr_get_ifindex(addr),
		"flags", rtnl_addr_get_flags(addr),
		"family", rtnl_addr_get_family(addr),
		"scope", rtnl_addr_get_scope(addr));
	if (data == NULL) {
		goto exit;
	}
	struct nl_addr *local = rtnl_addr_get_local(addr);
	if (local != NULL) {
		char buf[100];
		PyObject *ob = PyBytes_FromString(nl_addr2str(local, buf, 100));
		if (ob == NULL || PyDict_SetItemString(data, "local", ob) < 0) {
			Py_XDECREF(ob);
			goto exit;
		}
		Py_DECREF(ob);
	}
	PyObject *r = PyObject_CallMethod(listener->observer, "addr_change", "sO", act2str(act), data);
	Py_XDECREF(r);

  exit:
	Py_XDECREF(data);
	if (PyErr_Occurred()) {
		PyErr_Fetch(&listener->exc_typ, &listener->exc_val, &listener->exc_tb);
	}
}

static void _cb_addr(struct nl_cache *cache, struct nl_object *ob, int act,
                    void *data) {
	observe_addr_change(act, (struct rtnl_addr *)ob, (struct Listener*)data);
}

static void _e_addr(struct nl_object *ob, void *data) {
	observe_addr_change(NL_ACT_NEW, (struct rtnl_addr *)ob, (struct Listener*)data);
}

static void observe_route_change(
	int act,
	struct rtnl_route *route,
	struct Listener* listener)
{
	if (listener->exc_typ != NULL || listener->observer == Py_None) {
		return;
	}
	PyObject *data;
	char *cdst;
	char dstbuf[64];
	struct nl_addr* dst = rtnl_route_get_dst(route);
	if (dst == NULL || nl_addr_get_len(dst) == 0) {
		cdst = "default";
	} else {
		cdst = nl_addr2str(dst, dstbuf, sizeof(dstbuf));
	}

	int ifindex = -1;
	int nnexthops = rtnl_route_get_nnexthops(route);
	if (nnexthops > 0) {
		// Bit cheaty to ignore multipath but....
		struct rtnl_nexthop* nh = rtnl_route_nexthop_n(route, 0);
		ifindex = rtnl_route_nh_get_ifindex(nh);
	}
	data = Py_BuildValue(
		"{sB sB sI sy si}",
		"family", rtnl_route_get_family(route),
		"type", rtnl_route_get_type(route),
		"table", rtnl_route_get_table(route),
		"dst", cdst,
		"ifindex", ifindex);
	if (data == NULL) {
		goto exit;
	}
	PyObject *r = PyObject_CallMethod(listener->observer, "route_change", "sO", act2str(act), data);
	Py_XDECREF(r);

  exit:
	Py_XDECREF(data);
	if (PyErr_Occurred()) {
		PyErr_Fetch(&listener->exc_typ, &listener->exc_val, &listener->exc_tb);
	}
}

static void _cb_route(struct nl_cache *cache, struct nl_object *ob, int act,
                    void *data) {
	observe_route_change(act, (struct rtnl_route *)ob, (struct Listener*)data);
}

static void _e_route(struct nl_object *ob, void *data) {
	observe_route_change(NL_ACT_NEW, (struct rtnl_route *)ob, (struct Listener*)data);
}

static void
listener_dealloc(PyObject *self) {
	struct Listener* v = (struct Listener*)self;
	PyObject_GC_UnTrack(v);
	Py_CLEAR(v->observer);
	nl_cache_mngr_free(v->mngr);
	Py_CLEAR(v->exc_typ);
	Py_CLEAR(v->exc_val);
	Py_CLEAR(v->exc_tb);
	PyObject_GC_Del(v);
}

static int
listener_traverse(PyObject *self, visitproc visit, void *arg)
{
	struct Listener* v = (struct Listener*)self;
	Py_VISIT(v->observer);
	Py_VISIT(v->exc_typ);
	Py_VISIT(v->exc_val);
	Py_VISIT(v->exc_tb);
	return 0;
}

static PyTypeObject ListenerType;

static PyObject *
listener_new(PyTypeObject *type, PyObject *args, PyObject *kw)
{
	struct nl_cache_mngr *mngr;
	int r;

	r = nl_cache_mngr_alloc(NULL, NETLINK_ROUTE, NL_AUTO_PROVIDE, &mngr);
	if (r < 0) {
		PyErr_Format(PyExc_MemoryError, "nl_cache_mngr_alloc failed %d", r);
		return NULL;
	}

	struct Listener* listener = (struct Listener*)type->tp_alloc(type, 0);

	listener->mngr = mngr;

	Py_INCREF(Py_None);
	listener->observer = Py_None;

	return (PyObject*)listener;
}

static int
listener_init(PyObject *self, PyObject *args, PyObject *kw)
{
	PyObject* observer;

	char *kwlist[] = {"observer", 0};

	if (!PyArg_ParseTupleAndKeywords(args, kw, "O:listener", kwlist, &observer))
		return -1;

	struct Listener* listener = (struct Listener*)self;

	Py_CLEAR(listener->observer);
	Py_INCREF(observer);
	listener->observer = observer;

	return 0;
}

static PyObject*
maybe_restore(struct Listener* listener) {
	if (listener->exc_typ != NULL) {
		PyErr_Restore(listener->exc_typ, listener->exc_val, listener->exc_tb);
		listener->exc_typ = listener->exc_val = listener->exc_tb = NULL;
		return NULL;
	}
	Py_RETURN_NONE;
}

static PyObject*
listener_start(PyObject *self, PyObject* args)
{
	struct nl_cache *addr_cache, *route_cache;
	struct Listener* listener = (struct Listener*)self;
	int r;

	r = rtnl_link_alloc_cache(NULL, AF_UNSPEC, &listener->link_cache);
	if (r < 0) {
		PyErr_Format(PyExc_MemoryError, "rtnl_link_alloc_cache failed %d\n", r);
		return NULL;
	}

	r = nl_cache_mngr_add_cache(listener->mngr, listener->link_cache, _cb_link, listener);
	if (r < 0) {
		nl_cache_free(listener->link_cache);
		listener->link_cache = NULL;
		PyErr_Format(PyExc_RuntimeError, "nl_cache_mngr_add_cache failed %d\n", r);
		return NULL;
	}

	r = rtnl_addr_alloc_cache(NULL, &addr_cache);
	if (r < 0) {
		PyErr_Format(PyExc_MemoryError, "rtnl_link_alloc_cache failed %d\n", r);
		return NULL;
	}

	r = nl_cache_mngr_add_cache(listener->mngr, addr_cache, _cb_addr, listener);
	if (r < 0) {
		nl_cache_free(addr_cache);
		PyErr_Format(PyExc_RuntimeError, "nl_cache_mngr_add_cache failed %d\n", r);
		return NULL;
	}

	r = rtnl_route_alloc_cache(NULL, AF_UNSPEC, 0, &route_cache);
	if (r < 0) {
		PyErr_Format(PyExc_MemoryError, "rtnl_route_alloc_cache failed %d\n", r);
		return NULL;
	}

	r = nl_cache_mngr_add_cache(listener->mngr, route_cache, _cb_route, listener);
	if (r < 0) {
		nl_cache_free(route_cache);
		PyErr_Format(PyExc_RuntimeError, "nl_cache_mngr_add_cache failed %d\n", r);
		return NULL;
	}

	nl_cache_foreach(listener->link_cache, _e_link, self);
	nl_cache_foreach(addr_cache, _e_addr, self);
	nl_cache_foreach(route_cache, _e_route, self);

	return maybe_restore(listener);
}

static PyObject*
listener_fileno(PyObject *self, PyObject* args)
{
	struct Listener* listener = (struct Listener*)self;
	return PyLong_FromLong(nl_cache_mngr_get_fd(listener->mngr));
}

static PyObject*
listener_data_ready(PyObject *self, PyObject* args)
{
	struct Listener* listener = (struct Listener*)self;
        nl_cache_mngr_data_ready(listener->mngr);
	return maybe_restore(listener);
}

static PyObject*
listener_set_link_flags(PyObject *self, PyObject* args, PyObject* kw)
{
	int ifindex, flags;

	char *kwlist[] = {"ifindex", "flags", 0};

	if (!PyArg_ParseTupleAndKeywords(args, kw, "ii:set_link_flags", kwlist, &ifindex, &flags))
		return NULL;
	struct Listener* listener = (struct Listener*)self;
	struct rtnl_link *link = rtnl_link_get(listener->link_cache, ifindex);
	if (link == NULL) {
		PyErr_SetString(PyExc_RuntimeError, "link not found");
		return NULL;
	}
	struct nl_sock* sk = nl_socket_alloc();
	if (sk == NULL) {
		rtnl_link_put(link);
		PyErr_SetString(PyExc_MemoryError, "nl_socket_alloc() failed");
		return NULL;
	}
	int r = nl_connect(sk, NETLINK_ROUTE);
	if (r < 0) {
		rtnl_link_put(link);
		nl_socket_free(sk);
		PyErr_Format(PyExc_RuntimeError, "nl_connect failed %d", r);
		return NULL;
	}
	rtnl_link_set_flags(link, flags);
	r = rtnl_link_change(sk, link, link, 0);
	rtnl_link_put(link);
	nl_socket_free(sk);
	if (r < 0) {
		PyErr_Format(PyExc_RuntimeError, "rtnl_link_change failed %d", r);
		return NULL;
	}
	Py_RETURN_NONE;
}

static PyObject*
listener_unset_link_flags(PyObject *self, PyObject* args, PyObject* kw)
{
	int ifindex, flags;

	char *kwlist[] = {"ifindex", "flags", 0};

	if (!PyArg_ParseTupleAndKeywords(args, kw, "ii:unset_link_flags", kwlist, &ifindex, &flags))
		return NULL;
	struct Listener* listener = (struct Listener*)self;
	struct rtnl_link *link = rtnl_link_get(listener->link_cache, ifindex);
	if (link == NULL) {
		PyErr_SetString(PyExc_RuntimeError, "link not found");
		return NULL;
	}
	struct nl_sock* sk = nl_socket_alloc();
	if (sk == NULL) {
		rtnl_link_put(link);
		PyErr_SetString(PyExc_MemoryError, "nl_socket_alloc() failed");
		return NULL;
	}
	int r = nl_connect(sk, NETLINK_ROUTE);
	if (r < 0) {
		rtnl_link_put(link);
		nl_socket_free(sk);
		PyErr_Format(PyExc_RuntimeError, "nl_connect failed %d", r);
		return NULL;
	}
	rtnl_link_unset_flags(link, flags);
	r = rtnl_link_change(sk, link, link, 0);
	rtnl_link_put(link);
	nl_socket_free(sk);
	if (r < 0) {
		PyErr_Format(PyExc_RuntimeError, "rtnl_link_change failed %d", r);
		return NULL;
	}
	Py_RETURN_NONE;
}

static PyMethodDef ListenerMethods[] = {
	{"start", listener_start, METH_NOARGS, "XXX."},
	{"fileno", listener_fileno, METH_NOARGS, "XXX."},
	{"data_ready", listener_data_ready, METH_NOARGS, "XXX."},
	{"set_link_flags", (PyCFunction)listener_set_link_flags, METH_VARARGS|METH_KEYWORDS, "XXX."},
	{"unset_link_flags", (PyCFunction)listener_unset_link_flags, METH_VARARGS|METH_KEYWORDS, "XXX."},
	{},
};

static PyTypeObject ListenerType = {
	.ob_base = PyVarObject_HEAD_INIT(&PyType_Type, 0)
	.tp_name = "_rtnetlink.listener",
	.tp_basicsize = sizeof(struct Listener),

	.tp_dealloc = listener_dealloc,
	.tp_new = listener_new,
	.tp_init = listener_init,
	.tp_traverse = listener_traverse,

	.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,
	.tp_methods = ListenerMethods,
};

static struct PyModuleDef rtnetlink_module = {
   PyModuleDef_HEAD_INIT,
   "_rtnetlink",
};

PyMODINIT_FUNC
PyInit__rtnetlink(void)
{
    PyObject *m = PyModule_Create(&rtnetlink_module);

    if (m == NULL)
        return NULL;

    if (PyType_Ready(&ListenerType) < 0)
        return NULL;

    PyModule_AddObject(m, "listener", (PyObject *)&ListenerType);

    return m;
}
