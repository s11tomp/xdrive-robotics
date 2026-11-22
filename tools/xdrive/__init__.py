"""Host library for the XDRIVE Mini firmware: typed access to a board over USB (and CAN).

    from xdrive import usb
    from xdrive.props import odrv

    with usb.connect() as board:
        print(board.get(odrv.vbus_voltage))

`xdrive.props` names every property and function (generated from src/odrive-interface.yaml),
`xdrive.enums` the enums and error flags, `xdrive.board.Board` the operations.
"""
