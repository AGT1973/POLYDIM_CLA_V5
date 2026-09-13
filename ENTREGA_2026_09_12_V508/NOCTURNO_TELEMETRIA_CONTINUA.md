[2026-09-12 16:42:47] EXCEPCION CRÍTICA: 'charmap' codec can't encode character '\x8d' in position 23: character maps to <undefined>
Traceback (most recent call last):
  File "E:\POLYDIM_EINSOF\ENTREGA_2026_09_12_V508\polydim_v508_monolito_full.py", line 510, in <module>
    run_attack_battery()
    ~~~~~~~~~~~~~~~~~~^^
  File "E:\POLYDIM_EINSOF\ENTREGA_2026_09_12_V508\polydim_v508_monolito_full.py", line 432, in run_attack_battery
    print("POLYDIM V505 â€” BATERÃA DE ATAQUES ADVERSARIALES")
    ~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Python314\Lib\encodings\cp1252.py", line 19, in encode
    return codecs.charmap_encode(input,self.errors,encoding_table)[0]
           ~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
UnicodeEncodeError: 'charmap' codec can't encode character '\x8d' in position 23: character maps to <undefined>
[2026-09-12 16:46:25] EXCEPCION CRÍTICA: function 'pmtp_seqlock_get_write_buffer' not found
Traceback (most recent call last):
  File "E:\POLYDIM_EINSOF\ENTREGA_2026_09_12_V508\polydim_v508_monolito_full.py", line 510, in <module>
    run_attack_battery()
    ~~~~~~~~~~~~~~~~~~^^
  File "E:\POLYDIM_EINSOF\ENTREGA_2026_09_12_V508\polydim_v508_monolito_full.py", line 435, in run_attack_battery
    m = PmtpMonolito()
  File "E:\POLYDIM_EINSOF\ENTREGA_2026_09_12_V508\polydim_v508_monolito_full.py", line 255, in __init__
    self._load_libs()
    ~~~~~~~~~~~~~~~^^
  File "E:\POLYDIM_EINSOF\ENTREGA_2026_09_12_V508\polydim_v508_monolito_full.py", line 275, in _load_libs
    self._bind_rust_ffi()
    ~~~~~~~~~~~~~~~~~~~^^
  File "E:\POLYDIM_EINSOF\ENTREGA_2026_09_12_V508\polydim_v508_monolito_full.py", line 299, in _bind_rust_ffi
    lib.pmtp_seqlock_get_write_buffer.restype = ctypes.c_void_p
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Python314\Lib\ctypes\__init__.py", line 486, in __getattr__
    func = self.__getitem__(name)
  File "C:\Python314\Lib\ctypes\__init__.py", line 491, in __getitem__
    func = self._FuncPtr((name_or_ordinal, self))
AttributeError: function 'pmtp_seqlock_get_write_buffer' not found
