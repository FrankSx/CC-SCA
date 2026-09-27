/* sca_arsenal._native — x86-64 timing primitives
 * rdtsc with lfence serialization, clflush, timed load.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>
#include <string.h>

#if defined(__x86_64__) || defined(__i386__)
#include <x86intrin.h>
#define HAVE_X86 1
#else
#define HAVE_X86 0
#endif

static PyObject *native_rdtsc(PyObject *self, PyObject *args) {
#if HAVE_X86
    _mm_lfence();
    uint64_t t = __rdtsc();
    _mm_lfence();
    return PyLong_FromUnsignedLongLong(t);
#else
    struct timespec ts; (void)ts;
    PyErr_SetString(PyExc_RuntimeError, "rdtsc unavailable on this architecture");
    return NULL;
#endif
}

static PyObject *native_clflush(PyObject *self, PyObject *args) {
    unsigned long addr;
    if (!PyArg_ParseTuple(args, "k", &addr)) return NULL;
#if HAVE_X86
    _mm_clflush((void *)addr);
    _mm_mfence();
#endif
    Py_RETURN_NONE;
}

static PyObject *native_mfence(PyObject *self, PyObject *args) {
#if HAVE_X86
    _mm_mfence();
#endif
    Py_RETURN_NONE;
}

static PyObject *native_lfence(PyObject *self, PyObject *args) {
#if HAVE_X86
    _mm_lfence();
#endif
    Py_RETURN_NONE;
}

/* Time a single load from address. Serialized rdtsc around the access. */
static PyObject *native_time_load(PyObject *self, PyObject *args) {
    unsigned long addr;
    if (!PyArg_ParseTuple(args, "k", &addr)) return NULL;
#if HAVE_X86
    volatile char *p = (volatile char *)addr;
    _mm_mfence();
    _mm_lfence();
    uint64_t t0 = __rdtsc();
    _mm_lfence();
    (void)*p;
    _mm_lfence();
    uint64_t t1 = __rdtsc();
    _mm_lfence();
    return PyLong_FromUnsignedLongLong(t1 - t0);
#else
    PyErr_SetString(PyExc_RuntimeError, "timed loads unavailable on this architecture");
    return NULL;
#endif
}

/* Repeatedly access addr count times (drives lines into cache). */
static PyObject *native_touch(PyObject *self, PyObject *args) {
    unsigned long addr;
    int count = 1;
    if (!PyArg_ParseTuple(args, "k|i", &addr, &count)) return NULL;
    volatile char *p = (volatile char *)addr;
    char acc = 0;
    for (int i = 0; i < count; i++) acc ^= *p;
    (void)acc;
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"rdtsc", native_rdtsc, METH_NOARGS, "Serialised rdtsc() -> cycles"},
    {"clflush", native_clflush, METH_VARARGS, "clflush(addr)"},
    {"mfence", native_mfence, METH_NOARGS, "memory fence"},
    {"lfence", native_lfence, METH_NOARGS, "load fence"},
    {"time_load", native_time_load, METH_VARARGS, "time_load(addr) -> load latency in cycles"},
    {"touch", native_touch, METH_VARARGS, "touch(addr, count=1)"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT, "sca_arsenal._native", NULL, -1, methods
};

PyMODINIT_FUNC PyInit__native(void) {
    return PyModule_Create(&moduledef);
}
