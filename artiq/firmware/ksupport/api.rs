use board_misoc::csr;

macro_rules! api {
    ($i:ident) => ({
        extern { static $i: u8; }
        api!($i = &$i as *const _)
    });
    ($i:ident, $d:item) => ({
        $d
        api!($i = $i)
    });
    ($i:ident = $e:expr) => {
        (stringify!($i), unsafe { $e as *const () })
    }
}

pub fn resolve(required: &[u8]) -> Option<u32> {
    unsafe {
        API.iter()
           .find(|&&(exported, _)| exported.as_bytes() == required)
           .map(|&(_, ptr)| ptr as u32)
    }
}

#[allow(unused_unsafe)]
static mut API: &'static [(&'static str, *const ())] = &[
    api!(__divsi3),
    api!(__modsi3),
    api!(__ledf2),
    api!(__gedf2),
    api!(__unorddf2),
    api!(__eqdf2),
    api!(__ltdf2),
    api!(__nedf2),
    api!(__gtdf2),
    api!(__addsf3),
    api!(__subsf3),
    api!(__mulsf3),
    api!(__divsf3),
    api!(__lshrdi3),
    api!(__muldi3),
    api!(__divdi3),
    api!(__ashldi3),
    api!(__ashrdi3),
    api!(__udivmoddi4),
    api!(__floatsisf),
    api!(__floatunsisf),
    api!(__fixsfsi),
    api!(__fixunssfsi),
    api!(__adddf3),
    api!(__subdf3),
    api!(__muldf3),
    api!(__divdf3),
    api!(__floatsidf),
    api!(__floatunsidf),
    api!(__floatdidf),
    api!(__fixdfsi),
    api!(__fixdfdi),
    api!(__fixunsdfsi),
    api!(__udivdi3),
    api!(__umoddi3),
    api!(__moddi3),
    api!(__powidf2),

    /* libc */
    api!(memcmp, extern { fn memcmp(a: *const u8, b: *mut u8, size: usize); }),

    /* libm */
    // commented out functions are not available with the libm used here, but are available in NAR3.
    api!(acos),
    api!(acosh),
    api!(asin),
    api!(asinh),
    api!(atan),
    api!(atan2),
    api!(atanh),
    api!(cbrt),
    api!(ceil),
    api!(copysign),
    api!(cos),
    api!(cosh),
    api!(erf),
    api!(erfc),
    api!(exp),
    //api!(exp2),
    //api!(exp10),
    api!(expm1),
    api!(fabs),
    api!(floor),
    // api!(fmax),
    // api!(fmin),
    //api!(fma),
    api!(fmod),
    api!(hypot),
    api!(j0),
    api!(j1),
    api!(jn),
    api!(lgamma),
    api!(log),
    //api!(log2),
    api!(log10),
    api!(nextafter),
    api!(pow),
    api!(round),
    api!(sin),
    api!(sinh),
    api!(sqrt),
    api!(tan),
    api!(tanh),
    //api!(tgamma),
    //api!(trunc),
    api!(y0),
    api!(y1),
    api!(yn),

    /* exceptions */
    api!(_Unwind_Resume = ::unwind::_Unwind_Resume),
    api!(__artiq_personality = crate::eh_artiq::personality),
    api!(__artiq_raise = crate::eh_artiq::raise),
    api!(__artiq_reraise = crate::eh_artiq::reraise),

    /* proxified syscalls */
    api!(core_log),

    api!(now = csr::rtio::NOW_HI_ADDR as *const _),

    api!(rpc_send = crate::rpc_send),
    api!(rpc_send_async = crate::rpc_send_async),
    api!(rpc_recv = crate::rpc_recv),

    api!(cache_get = crate::cache_get),
    api!(cache_put = crate::cache_put),

    /* direct syscalls */
    api!(rtio_init = crate::rtio::init),
    api!(rtio_get_destination_status = crate::rtio::get_destination_status),
    api!(rtio_get_counter = crate::rtio::get_counter),
    api!(rtio_log),
    api!(rtio_output = crate::rtio::output),
    api!(rtio_output_wide = crate::rtio::output_wide),
    api!(rtio_input_timestamp = crate::rtio::input_timestamp),
    api!(rtio_input_data = crate::rtio::input_data),
    api!(rtio_input_timestamped_data = crate::rtio::input_timestamped_data),

    api!(dma_record_start = crate::dma_record_start),
    api!(dma_record_stop = crate::dma_record_stop),
    api!(dma_erase = crate::dma_erase),
    api!(dma_retrieve = crate::dma_retrieve),
    api!(dma_playback = crate::dma_playback),

    api!(i2c_start = crate::nrt_bus::i2c::start),
    api!(i2c_restart = crate::nrt_bus::i2c::restart),
    api!(i2c_stop = crate::nrt_bus::i2c::stop),
    api!(i2c_write = crate::nrt_bus::i2c::write),
    api!(i2c_read = crate::nrt_bus::i2c::read),

    api!(spi_set_config = crate::nrt_bus::spi::set_config),
    api!(spi_write = crate::nrt_bus::spi::write),
    api!(spi_read = crate::nrt_bus::spi::read),
];
