use std::error::Error;
use std::fs::File;

use vx_runtime_consumer_contract::{ContractRequest, verify_and_launch};

fn main() -> Result<(), Box<dyn Error>> {
    let mut arguments = std::env::args_os().skip(1);
    let path = arguments
        .next()
        .ok_or("a consumer request JSON file is required")?;
    if arguments.next().is_some() {
        return Err("expected exactly one consumer request JSON file".into());
    }
    let request: ContractRequest = serde_json::from_reader(File::open(path)?)?;
    let receipt = verify_and_launch(&request)?;
    println!(
        "VX_REZ_CONSUMER_RECEIPT {}",
        serde_json::to_string(&receipt)?
    );
    Ok(())
}
